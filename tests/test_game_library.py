#!/usr/bin/env python3
import errno
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('game_library',Path(__file__).resolve().parents[1]/'port/game_library.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class BiosImport(unittest.TestCase):
 def test_no_space_cleans_partial_then_retry(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'scph5501.bin';source.write_bytes(b'B'*(512*1024));dest_dir=root/'firmware';dest_dir.mkdir();dest=dest_dir/source.name
   def fail(original,output):
    output.write(b'partial')
    raise OSError(errno.ENOSPC,'Injected full disk')
   with patch.object(module.shutil,'copyfileobj',side_effect=fail):
    with self.assertRaises(OSError):module.import_bios(source,dest)
   self.assertEqual(list(dest_dir.iterdir()),[])
   module.import_bios(source,dest)
   self.assertEqual(dest.read_bytes(),source.read_bytes())
   self.assertEqual(dest.stat().st_mode&0o777,0o600)
   self.assertEqual(list(dest_dir.iterdir()),[dest])
 def test_existing_firmware_preserved(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'scph5500.bin';source.write_bytes(b'B'*(512*1024));dest_dir=root/'firmware';dest_dir.mkdir();dest=dest_dir/source.name;dest.write_bytes(b'existing')
   with self.assertRaises(FileExistsError):module.import_bios(source,dest)
   self.assertEqual(dest.read_bytes(),b'existing');self.assertEqual(list(dest_dir.iterdir()),[dest])
 def test_bad_size_never_creates_temporary(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'scph5502.bin';source.write_bytes(b'short');dest_dir=root/'firmware';dest_dir.mkdir()
   with self.assertRaises(ValueError):module.import_bios(source,dest_dir/source.name)
   self.assertEqual(list(dest_dir.iterdir()),[])
if __name__=='__main__':unittest.main()
