# 参与贡献

感谢你愿意改进昔夕。

## 开始之前

- 不要提交 API 密钥、QQ 号、聊天记录、记忆数据库、日志或本机绝对路径。
- 不要提交模型权重、训练音频、第三方运行时、安装包或其他大文件。
- 不要提交没有明确再分发许可的角色美术、声音或数据集。
- 功能行为变化应同时更新测试和用户文档。

## 本地检查

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe scripts\audit_repository.py
node --check studio\app.js
node --check studio\setup.js
node --check studio\call_overlay.js
```

提交说明应简洁描述行为变化。问题修复需要写明复现方式、根因和验证结果。
