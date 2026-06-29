# 多智能体动态编排框架

一个基于 FastAPI 的轻量级多智能体任务编排框架，用于实验动态任务路由、工具调用、事件回放、研究型问答和结果产物生成。

## 项目简介

本项目接收自然语言任务，根据任务类型自动选择执行流程，必要时调用安全工具，记录执行事件，并通过 API 和浏览器界面返回结构化结果。

适合用于：

- 构建带引用来源的研究型问答流程。
- 对比不同多智能体工作流的执行效果。
- 演示任务路由、工具调用、执行图和事件回放。
- 生成任务级 Markdown、文本、JSON、CSV 或 ZIP 产物。
- 作为多智能体编排、RAG/Research Agent、工具代理等方向的实验底座。

## 功能特性

| 模块 | 说明 |
| --- | --- |
| 后端服务 | 基于 FastAPI，使用 SQLite 持久化任务、事件和结果 |
| 模型接入 | OpenAI 兼容接口，支持 DeepSeek 等兼容服务配置 |
| 工作流 | 支持 `direct`、`plan_execute`、`research`、`react`、`supervisor`、`dag`、`swarm` |
| 工具系统 | 支持搜索、安全网页抓取、天气、时间、计算器、日期、单位换算等工具 |
| 结果产物 | 支持生成 Markdown、文本、JSON、CSV 和 ZIP 文件 |
| 可观测性 | 支持事件历史、SSE 流、任务回放和执行图事件 |
| 测试覆盖 | 使用 pytest 覆盖工作流、工具、API、产物和安全逻辑 |

## 界面预览

启动服务后访问：

```text
http://127.0.0.1:8000/ui
```

前端界面支持任务提交、会话选择、任务状态查看、最终结果渲染、引用来源展示、产物下载、执行图查看和任务回放。

## 快速启动

建议在已有 Python/Conda 环境中运行。当前项目验证环境使用 `pytorch` Conda 环境。

```powershell
conda run -n pytorch python -m pytest
conda run -n pytorch python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

然后打开：

```text
http://127.0.0.1:8000/ui
```

## 环境变量

真实调用大模型时需要配置：

```powershell
$env:LLM_BASE_URL='https://api.deepseek.com'
$env:LLM_API_KEY='your-api-key'
$env:LLM_MODEL='deepseek-chat'
```

研究任务和工具调用可选配置：

```powershell
$env:TAVILY_API_KEY='your-tavily-key'
$env:WEATHER_API_KEY='your-weatherapi-key'
$env:ARTIFACT_ROOT='artifacts'
```

项目支持本地 `.env` 文件。请不要将 `.env` 提交到 Git。

## 示例任务

```text
查询北京天气和当前本地时间
```

```text
调研特斯拉公司，概括业务、财务、竞争格局和近期动态，并给出引用来源
```

```text
先调研特斯拉公司基本情况，再分析其竞争格局，最后生成风险报告
```

```text
生成一份多智能体框架调研报告，并保存为 Markdown 文件
```

## 项目结构

```text
app/
  main.py                  FastAPI 应用入口和路由挂载
  api/                     API 路由
  core/                    配置、枚举和通用错误
  db/                      SQLite 初始化和仓储方法
  llm/                     大模型客户端封装
  orchestration/           任务路由、提示词、JSON 修复和编排逻辑
  agents/                  子智能体运行辅助模块
  tools/                   工具注册、工具策略、执行器和内置工具
  services/                任务、事件、结果和产物服务
  schemas/                 请求、响应和数据结构定义
  static/                  浏览器前端界面
  workflows/               工作流相关实现
tests/                     自动化测试
scripts/                   可选的真实服务验证脚本
docs/                      设计说明和实施记录
```

## API 概览

主要接口：

- `POST /tasks`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/stream`
- `GET /tasks/{task_id}/result`
- `GET /tasks/{task_id}/replay`
- `GET /tasks/{task_id}/artifacts`
- `POST /tasks/{task_id}/cancel`
- `POST /sessions`
- `POST /sessions/{session_id}/tasks`

## 测试

```powershell
conda run -n pytorch python -m pytest
conda run -n pytorch ruff check app tests
```

自动化测试使用模拟的大模型、搜索和天气响应，通常不需要外部 API Key。

## 当前限制

- 当前定位是本地研究和演示框架，不是生产级多租户服务。
- 暂未提供认证、权限和用户隔离能力。
- 默认使用 SQLite 和本地文件作为持久化方案。
- 编排器目前保持集中式实现，后续可按模块继续拆分。
- 真实研究质量取决于配置的大模型和搜索服务。

## 许可证

如果需要公开发布项目，建议补充明确的开源许可证文件。
