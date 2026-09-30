#!/usr/bin/env python3
"""Check release hashes, metadata/control identity and Store complete payloads.

Pass the project's current Store validator; this command never installs/sends.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--store-validator',type=Path,required=True);parser.add_argument('--simulate-dependencies',action='store_true');args=parser.parse_args()
 spec=importlib.util.spec_from_file_location('store_publication',args.store_validator);validator=importlib.util.module_from_spec(spec);sys.modules[spec.name]=validator;spec.loader.exec_module(validator)
 results=[];debs=[]
 for path in sorted((ROOT/'packages').glob('*/app.json')):
  meta=json.loads(path.read_text());app=meta['application'];release=meta['release'];deb=path.parent/release['file'];fields=validator.package_fields(deb)
  assert hashlib.sha256(deb.read_bytes()).hexdigest()==release['sha256']
  assert fields['Package']==app['package'] and fields['Version']==release['version']
  assert fields['X-Typix-Compatible-OS']=='raspios-trixie'
  size=validator.verify_complete_payload(deb,app)
  for image in meta['screenshots']:
   assert (path.parent/image['path']).is_file(), image
  results.append({'package':app['package'],'architecture':fields['Architecture'],'payloadBytes':size,'compatibleOS':fields['X-Typix-Compatible-OS'],'completePayload':True})
  debs.append(str(deb))
 assert len(results)==15
 dependency_status=None
 if args.simulate_dependencies:
  result=subprocess.run(['apt-get','-s','install',*debs],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  (ROOT/'build/dependency-simulation.log').write_text(result.stdout)
  dependency_status=result.returncode
  assert result.returncode==0,'Dependency simulation failed; see build/dependency-simulation.log'
 output={'packages':results,'dependencySimulationExit':dependency_status,'installed':False}
 (ROOT/'build/package-check.json').write_text(json.dumps(output,indent=2)+'\n')
 print(f'{len(results)} Store complete payloads, hashes and metadata passed; dependency simulation exit={dependency_status}; installed=False')
if __name__=='__main__':main()
