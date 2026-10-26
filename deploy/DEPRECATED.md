# ⚠️ 已弃用（2026-10-26）

此目录 **不再用于部署**。

部署已迁移到 `../public/`，原因是需要走 `new-application` 路由以获得**可读固定域名**：
https://portfolio-snapshot-31273.app.workbuddy.host/?sharecode=VN543KH6HH

若仍向本目录部署，会命中 `legacy-sandbox` 路由，得到乱码域名
`<sandboxId>.bj9.agentos-app.net`（由目录路径 sha256 决定，改不了）。

详见 ../SKILL.md 步骤 7。
