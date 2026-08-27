# 昔夕

昔夕是一款面向 Windows 的本地 AI 陪伴应用，集成文字聊天、图片理解、完整音频语音回复、QQ、长期记忆、持续成长、天气提醒和游戏画面陪伴。

当前公开版：`0.1`

## 开源状态

昔夕的原创软件源代码以 [Apache License 2.0](LICENSE) 开源，可以在遵守许可证的前提下使用、研究、修改和分发。

训练音色、模型权重、参考音频、角色图像、名称与标识不在代码许可证的授权范围内；第三方组件继续遵守各自许可证。完整边界见 [开源授权说明](docs/LICENSING.md) 和 [第三方声明](THIRD_PARTY_NOTICES.md)。

## 主要功能

- 独立配置语言模型与视觉模型，支持 OpenAI 兼容接口及自定义中转网关
- 中文、日语、英语本地语音回复，以及麦克风语音输入和通话
- QQ 私聊、群聊、扫码登录、名称或 `@` 唤醒和可控的主动参与
- 跨会话长期记忆、兴趣成长、联网学习和可解释的情感状态
- 天气查询、极端天气提醒和可编辑城市
- 观察游戏画面并提供自然的陪伴、鼓励、吐槽和建议
- 本地桌面应用、首次启动配置中心、组件检测和按需安装

游戏陪伴只读取用户主动开启后的屏幕画面并进行交流，不控制键盘或鼠标，也不会学习或复现用户的操作。

## 下载与安装

1. 在安装包通过资源授权复核并正式发布后，从 GitHub 的 **Releases** 页面下载 `Xixi-Setup.exe` 和 `SHA256SUMS.txt`。
2. 对照 SHA-256 校验值确认安装包完整。
3. 运行安装程序并选择安装位置。
4. 首次启动会先进入配置中心；语言模型和视觉模型也可以暂时跳过，之后在设置中完成。
5. QQ、语音识别、本地语音等组件可在“设置 > 环境配置”中按需安装。

支持 Windows 10/11 x64。部分本地模型较大，首次安装或首次加载需要一定时间。

### 麦克风权限

首次开始语音输入、语音通话或游戏陪伴通话时，应用会显示麦克风授权面板。若曾误点拒绝，可前往“设置 > 基础与启动 > 设备权限”重新开启并检测麦克风；Windows 全局权限关闭时，可从同一页面打开系统麦克风设置。

## 模型配置

语言模型和视觉模型可以使用不同供应商。每个连接独立保存：

- API 地址
- API 密钥
- 模型名称
- 接口检测结果

API 密钥通过当前 Windows 用户的凭据管理器保存，不写入公开配置文件。不要在问题反馈、日志截图或 Git 提交中粘贴真实密钥。

## 数据与隐私

公开版首次安装不会包含制作者的聊天记录、记忆、QQ 账号、API 密钥、天气城市或浏览器缓存。运行后产生的数据保存在安装位置对应的用户数据目录中。

详细说明见 [隐私与本地数据](docs/PRIVACY.md)。常见问题见 [故障排查](docs/TROUBLESHOOTING.md)。

## 本地开发

```powershell
git clone <repository-url>
cd Xixi
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

启动源码版：

```powershell
.\.venv\Scripts\python.exe start_xixi_desktop.py
```

公开仓库不会提交个人运行数据、训练模型、参考音频、下载后的第三方组件或构建输出。构建正式安装包前，需要由维护者在本地准备有权分发的私有发布资源。

## 发布构建

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\packaging\build_public_release.ps1
```

构建流程会依次执行 Python 编译检查、完整单元测试、JavaScript 语法检查、语音回归检查、隐私审计、公开版冒烟测试和安装包生成。生成的安装包只能作为 GitHub Release 附件上传，不能直接提交到 Git 仓库。

发布步骤见 [发布清单](docs/RELEASING.md)。

## 项目结构

```text
app/                 后端、模型、QQ、记忆、语音和环境服务
studio/              桌面界面
tests/               自动化测试
scripts/             审计、验证和发布工具
packaging/           Windows 公开版构建配置
docs/                安装、隐私、排障和发布文档
```

## 授权与第三方组件

昔夕原创软件源代码使用 [Apache License 2.0](LICENSE)。角色资源、训练音色和模型等不属于该代码许可证，详情见 [开源授权说明](docs/LICENSING.md)。

昔夕包含或可调用多个第三方项目。各组件继续受其原许可证约束，详情见 [第三方声明](THIRD_PARTY_NOTICES.md)。其中 NapCatQQ 的再分发仅限非商业用途。

训练模型、参考音频和角色美术不因源码公开而自动获得再使用或再分发授权。公开发布安装包前，维护者仍需确认这些资源拥有覆盖 GitHub 发布的授权范围。
