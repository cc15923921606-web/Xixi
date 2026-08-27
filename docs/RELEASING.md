# 发布清单

## 发布前

- 更新版本号和 `CHANGELOG.md`
- 确认个人数据、密钥、训练素材和模型权重未进入 Git 暂存区
- 确认所有捆绑组件具备再分发授权并附带许可证
- 运行仓库审计和完整测试
- 构建公开安装包并完成公开版冒烟测试
- 在干净 Windows 用户环境中至少完成一次安装、首次配置、麦克风授权恢复、QQ 登录和卸载测试

## 本地命令

```powershell
.\venv\Scripts\python.exe scripts\audit_repository.py
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
pwsh -NoProfile -ExecutionPolicy Bypass -File .\packaging\build_public_release.ps1
```

## GitHub Release

1. 创建与版本一致的标签，例如 `v0.1`。
2. 使用 `CHANGELOG.md` 对应版本作为发布说明基础。
3. 只上传安装包和 `SHA256SUMS.txt`，不要把安装包提交到 Git。
4. 下载一次已上传的附件并重新校验 SHA-256。
5. Release 正式公开前先保持草稿状态完成复核。
