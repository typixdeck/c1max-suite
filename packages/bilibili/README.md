# Typix Bilibili

热门、搜索、BV、分 P、扫码登录与直连 MP4。

0.2.1 修复 HTTPS 视频请求缺少 Referer / User-Agent 导致的 403；使用系统 CA 验证证书，账号 Cookie 不发给视频 CDN。界面保持 0.2.0 布局，截图仍明确标注为 0.2.0 的 ARM64 GTK 参考图。

完整 deb、原生界面、用户数据与软件包分离。构建源位于父级 C1Max suite；运行 `python3 tools/build_debs.py --repository typixdeck/c1max-suite --apps bilibili --version 0.2.1-1` 构建该应用。软件包仅兼容官方 Raspberry Pi OS trixie ARM64。

见随包 PORT-STATUS.md 的具体支持范围和硬件限制。需要媒体服务/ROM/BIOS/USB 节点的功能不会因安装软件包而自动具备。截图来源与验证范围见 app.json，源码渲染和旧版本参考图不表示本次 CM4 实体硬件已验收。
