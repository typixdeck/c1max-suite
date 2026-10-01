# Typix Piano

键盘和触控复音钢琴与正常桌面音频输出。

完整 deb、原生界面、用户数据与软件包分离。构建源位于父级 C1Max suite；运行 `python3 tools/build_debs.py --repository OWNER/REPO --apps piano` 构建该应用。软件包仅兼容官方 Raspberry Pi OS trixie ARM64。

见随包 PORT-STATUS.md 的具体支持范围和硬件限制。需要媒体服务/ROM/BIOS/USB 节点的功能不会因安装软件包而自动具备。截图来源与验证范围见 app.json，源码渲染和旧版本参考图不表示本次 CM4 实体硬件已验收。
