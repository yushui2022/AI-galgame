# 参与开发

欢迎提交问题、文档和代码。请不要在 Issue、日志、截图或测试数据中上传 API Key、真实聊天记录或付费生成媒体。

## 本地检查

```bash
uv sync --extra dev
uv run ruff check backend
uv run pytest -q

cd frontend
npm install
npm run typecheck
npm run build
```

涉及用户流程时还应运行 `npm run test:e2e`。Playwright 测试使用假供应商。

## 设计原则

- Turn 保持不可变，续写只追加节点。
- 分支事实必须按祖先链隔离。
- 自由输入是玩家行动，不是系统提示词。
- API Key 不进入浏览器存储、接口响应或日志。
- 媒体先下载到本地，再向玩家报告成功。
- 新供应商实现统一 Provider 契约，不在 UI 和编排器中散落供应商判断。
- SFW 审核失败时可以安全改写，但不绕过供应商审核。

提交前请确认新文件许可证兼容 Apache-2.0，并在复用第三方内容时更新 `NOTICE`。
