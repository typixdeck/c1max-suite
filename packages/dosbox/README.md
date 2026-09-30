# Typix DOSBox

本地 DOS 游戏目录、完整 DOSBox 运行与会话管理。

完整 deb、原生界面、用户数据与软件包分离。构建源位于父级 C1Max suite；运行 `python3 tools/build_debs.py --repository OWNER/REPO` 构建全部应用。软件包仅兼容官方 Raspberry Pi OS trixie ARM64。

见随包 PORT-STATUS.md 的具体支持范围和硬件限制。需要媒体服务/ROM/BIOS/USB 节点的功能不会因安装软件包而自动具备。截图为真实 CM4 隔离显示测试，不表示外部硬件已验收。
