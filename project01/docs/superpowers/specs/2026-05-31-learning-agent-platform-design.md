# 专业领域知识学习 Agent 平台第一版设计规格

## 1. 项目定位

本项目第一版定位为演示型完整闭环项目，主题是专业领域知识学习 Agent 平台。目标不是生产级学习平台，而是展示一条完整 AI 应用技术路线：

用户注册登录 -> 创建知识库 -> 上传学习资料 -> 构建 RAG 索引 -> 创建学习会话 -> Agent 自动选库或进入通用模式 -> 生成学习路径 -> 分阶段问答辅导 -> 生成测验 -> 评分反馈 -> 调整学习路径 -> 阶段摘要与会话总结。

第一版重点关注后端、RAG 和 Agent 能力设计。前端需要清晰展示最终效果，但不优先考虑移动端、多端适配、高并发、复杂权限或生产级运维。

## 2. 已确认范围

### 2.1 第一版目标

- 做完整学习闭环，而不是单点功能 demo。
- Agent 能力是项目重点，不能只是简单包装 LLM。
- 不接入互联网搜索。
- 不内置演示数据，演示时由用户真实注册、建库、上传资料。
- 不引入后台任务队列。
- 不使用 FAISS，第一版只使用 Chroma。
- Django 只作为未来管理后台扩展方向，不进入当前运行服务。

### 2.2 用户与认证

- 支持多用户。
- 注册只需要账号和密码。
- 使用 Session Cookie 认证。
- 密码哈希存储。
- 不需要管理员角色。
- 所有用户权限相同。
- 不同用户的数据完全隔离。

### 2.3 知识库

- 每个用户可以创建多个知识库。
- 知识库为用户私有数据。
- 知识库字段保持轻量：
  - 名称必填。
  - 简介、标签选填。
  - 创建时间、更新时间、资料数量、学习进度由系统维护。
  - 摘要、关键词、知识点可由 Agent 懒生成并缓存。
- 用户可以删除知识库。
- 删除知识库时物理删除相关文档、上传文件、向量索引、学习进度和相关信息。
- 删除操作需要二次确认。

### 2.4 文档上传

- 支持 PDF、Markdown、TXT。
- 上传后同步完成解析、清洗、切分、Embedding 和写入 Chroma。
- 上传状态只展示上传中、已完成、失败。
- 第一版使用固定切分策略，不提供用户可配置 chunk 参数。
- 文件大小、数量和容量限制在实现阶段确定。
- 知识点抽取不在上传时强制执行，而是在 Agent 首次使用知识库、生成学习路径或查看知识库详情时懒触发并缓存。

### 2.5 学习会话

- 用户创建学习会话时只需要输入学习主题。
- 不强制每次上传资料。
- Agent 优先从用户已有知识库中选择最相关的一个。
- 没有相关知识库时进入通用学习模式。
- 通用学习模式使用模型内部知识，不接入互联网搜索，并明确提示未引用用户资料。
- 会话的知识库绑定可为空、可自动选择、可由用户修改。
- Agent 如果发现另一个知识库更相关，只建议切换，不自动切换；是否切换由用户确认。
- 用户手动选择知识库的优先级高于 Agent 自动选择。

### 2.6 学习路径

学习路径用于帮助用户理解学习顺序，也用于辅助 Agent 推进学习交互。第一版采用纵向时间线展示。

阶段字段包括：

- 阶段主题。
- 知识点信息。
- 阶段状态：未开始、学习中、已完成。
- 学习进度：0-100。
- 简短说明，可为空。

不把推荐资料、预计时间、练习任务、前置依赖作为第一版路径字段。推荐资料和练习由 Agent 在交互中动态生成。

学习路径允许用户手动编辑，包括新增、删除、调整顺序、修改阶段主题、说明和知识点。

### 2.7 阶段推进

- 用户可以手动开始或完成阶段。
- 测验准确率达到 80% 及以上时，Agent 建议进入下一阶段。
- 是否推进由用户确认。
- 60%-80% 给复习建议。
- 低于 60% 触发路径调整或补强学习建议。

### 2.8 测验与反馈

- Agent 一次生成 3-5 道小测验题。
- 前端逐题展示，用户完成后统一提交。
- 题型以选择题、判断题、简答题为主。
- 客观题直接判分。
- 简答题由 LLM 根据参考答案和评分标准给分，并给出简短评语。
- 简答题得分折算进总准确率。
- 低于 60% 自动调整学习路径。
- 60%-80% 给复习建议，不自动覆盖路径。
- 80% 及以上建议进入下一阶段。

### 2.9 聊天记录与总结

- 每次学习会话的用户消息和 Agent 回复全部保存。
- 聊天记录主要用于历史回顾、继续会话、阶段反馈。
- 阶段完成时可以生成阶段摘要。
- 用户手动结束会话时生成最终会话总结。
- 最终总结包含会话主题、标签、学习摘要、掌握情况和后续建议。
- 会话主题和标签尽量与知识库名称/标签体系保持一致。
- 不同主题的历史会话不参与当前学习分析。
- 第一版不做复杂长期记忆，只做当前会话和同主题摘要的轻量利用。

## 3. 技术选型

### 3.1 后端与前端

- 后端：FastAPI。
- 前端：FastAPI templates + 原生 JavaScript。
- 数据库：SQLite。
- 认证：Session Cookie。
- ORM：SQLAlchemy。

### 3.2 Agent 与模型

- Agent 编排：LangGraph。
- LangChain 可以少量使用，但不作为主架构核心。
- 文本生成模型：DeepSeek，使用 OpenAI-compatible API。
- Embedding 模型：Qwen Embedding，使用 OpenAI-compatible API。
- 具体 API key、base URL、模型名在实现阶段由用户提供。

建议配置：

```text
LLM_API_KEY
LLM_BASE_URL
LLM_MODEL

EMBEDDING_API_KEY
EMBEDDING_BASE_URL
EMBEDDING_MODEL
```

### 3.3 向量检索

- 第一版只使用 Chroma。
- Chroma 负责 chunk embedding、持久化、metadata 和相似度检索。
- SQLite 保存业务数据。
- FAISS 作为未来扩展，不进入第一版核心实现。

## 4. 后端架构

后端采用 FastAPI 单体应用，不拆微服务。建议目录：

```text
backend/
  app/
    main.py
    core/
    db/
    models/
    schemas/
    routers/
    services/
    agents/
    templates/
    static/
  data/
    uploads/
    chroma/
```

分层职责：

- `routers` 处理 HTTP 请求、登录校验、参数校验和响应组装。
- `services` 处理业务逻辑，例如文档解析、Chroma 写入、知识库删除、测验评分结果保存。
- `agents` 负责 LangGraph 状态、节点和图定义，不直接处理 HTTP。
- `core` 封装配置、安全、Session、DeepSeek LLM client 和 Qwen Embedding client。
- `db` 管理 SQLite 连接和初始化。

第一版模块：

- `auth`：注册、登录、退出、当前用户。
- `knowledge_bases`：创建、列表、详情、编辑、删除。
- `documents`：上传、解析、切分、embedding、写入 Chroma、删除。
- `learning_sessions`：创建会话、获取会话、聊天、阶段操作、结束总结。
- `learning_paths`：生成路径、编辑路径、更新阶段状态、Agent 调整路径。
- `quizzes`：生成测验、提交答案、评分、反馈、触发路径调整。
- `agent_runtime`：选库、检索、回答、讲解、测验、总结、路径调整。

## 5. LangGraph Agent 设计

### 5.1 设计原则

- 固定主流程保证演示闭环稳定。
- 聊天阶段允许有限动态路由。
- 学习路径是 Agent 推进学习的共享状态。
- 知识库可以为空，进入通用学习模式。
- Agent 可以建议切换知识库，但不自动切换，除非用户确认。
- 不做无限自主循环，不让 Agent 反复规划和调用工具。

### 5.2 AgentState

```text
AgentState
  user_id
  session_id
  topic
  current_message
  conversation_history
  knowledge_base_id
  selection_mode
  is_general_mode
  selected_stage_id
  learning_path
  retrieved_documents
  retrieved_chunks
  intent
  quiz
  quiz_result
  feedback
  path_adjustment_reason
  summary
  errors
```

`selection_mode` 可取：

- `auto`
- `manual`
- `none`

如实现时需要表示“Agent 建议后用户确认”，可以增加 `auto_confirmed`，也可以简化为 `manual`。

### 5.3 Agent 节点

- `diagnose_session`：根据学习主题和已有会话信息生成初始学习假设。
- `select_knowledge_base`：根据学习主题、知识库名称、简介、标签、文件名、已有知识点和摘要选择最相关知识库。
- `extract_knowledge_points_if_needed`：在需要路径或知识库详情时触发知识点抽取并缓存。
- `retrieve_context`：从当前知识库的 Chroma collection 中检索相关 chunks。
- `generate_learning_path`：生成结构化学习路径。
- `route_learning_intent`：判断聊天意图。
- `tutor_response`：基于当前阶段、检索内容和上下文生成 Markdown 辅导回答。
- `generate_quiz`：基于当前阶段生成 3-5 道题。
- `grade_quiz`：客观题直接判分，简答题调用 LLM 评分。
- `generate_feedback`：根据测验结果生成掌握情况、薄弱点和建议。
- `adjust_learning_path`：用户主动要求或低分触发时覆盖当前路径。
- `summarize_stage`：阶段完成时生成阶段摘要。
- `summarize_session`：用户手动结束会话时生成最终总结。

### 5.4 图流程

建议拆成 4 条图，而不是一个巨大图：

```text
session_start_graph
  diagnose_session
  -> select_knowledge_base
  -> extract_knowledge_points_if_needed
  -> generate_learning_path

chat_graph
  route_learning_intent
  -> retrieve_context
  -> tutor_response
  或 -> generate_quiz
  或 -> adjust_learning_path
  或 -> suggest_knowledge_base_switch

quiz_graph
  generate_quiz
  -> grade_quiz
  -> generate_feedback
  -> maybe_adjust_learning_path

summary_graph
  summarize_stage
  或 summarize_session
```

聊天意图包括：

- `ask_question`
- `explain_concept`
- `request_quiz`
- `request_path_adjustment`
- `off_topic_or_new_topic`
- `general_chat`

## 6. 数据模型

### 6.1 users

```text
id
username
password_hash
created_at
updated_at
```

### 6.2 knowledge_bases

```text
id
user_id
name
description
tags_json
summary
keywords_json
created_at
updated_at
```

### 6.3 documents

```text
id
user_id
knowledge_base_id
filename
original_filename
file_type
file_size
storage_path
status
error_message
chunk_count
created_at
```

Chroma chunk metadata：

```text
user_id
knowledge_base_id
document_id
filename
chunk_index
```

### 6.4 learning_sessions

```text
id
user_id
topic
title
tags_json
knowledge_base_id
selection_mode
selection_reason
is_general_mode
current_stage_id
status
summary
mastery_summary
next_suggestions
created_at
updated_at
ended_at
```

### 6.5 learning_path_stages

```text
id
session_id
order_index
title
description
knowledge_points_json
status
progress
stage_summary
created_at
updated_at
```

### 6.6 chat_messages

```text
id
session_id
user_id
role
content
source_documents_json
created_at
```

### 6.7 quizzes

```text
id
session_id
stage_id
title
questions_json
status
created_at
submitted_at
```

### 6.8 quiz_results

```text
id
quiz_id
session_id
stage_id
answers_json
grading_json
accuracy
feedback
triggered_path_adjustment
created_at
```

### 6.9 agent_events

```text
id
session_id
event_type
message
payload_json
created_at
```

`agent_events` 只记录对学习状态有意义的关键事件，不作为详细调试日志。

## 7. API 与页面

### 7.1 页面

```text
/auth/login
/auth/register
/app
/app/knowledge-bases
/app/knowledge-bases/{id}
/app/sessions/{id}
/app/me
```

学习工作台 `/app/sessions/{id}` 是核心演示页面：

- 左侧：纵向学习路径。
- 中间：聊天窗口。
- 右侧：当前知识库或通用模式、当前阶段、测验入口、测验结果。

界面只展示轻量 Agent 状态：

- 正在选择知识库。
- 正在检索资料。
- 正在生成学习路径。
- 正在生成测验。
- 正在评分。
- 正在总结。

### 7.2 API

认证：

```text
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
GET  /api/me
```

知识库：

```text
POST   /api/knowledge-bases
GET    /api/knowledge-bases
GET    /api/knowledge-bases/{id}
PUT    /api/knowledge-bases/{id}
DELETE /api/knowledge-bases/{id}
```

文档：

```text
POST   /api/knowledge-bases/{id}/documents/upload
GET    /api/knowledge-bases/{id}/documents
DELETE /api/documents/{id}
```

学习会话：

```text
POST /api/learning/sessions
GET  /api/learning/sessions
GET  /api/learning/sessions/{id}
POST /api/learning/sessions/{id}/end
```

学习路径：

```text
PUT  /api/learning/sessions/{id}/path
POST /api/learning/sessions/{id}/path/adjust
POST /api/learning/sessions/{id}/stages/{stage_id}/start
POST /api/learning/sessions/{id}/stages/{stage_id}/complete
```

聊天：

```text
POST /api/learning/sessions/{id}/chat
```

聊天接口支持流式输出，建议使用 SSE：

```text
event: status
event: token
event: sources
event: suggestion
event: done
event: error
```

测验：

```text
POST /api/learning/sessions/{id}/quiz
POST /api/learning/sessions/{id}/quiz/{quiz_id}/submit
```

## 8. 错误处理与降级

### 8.1 权限

- 未登录访问页面跳转登录页。
- 未登录访问 API 返回 401。
- 资源不存在或不属于当前用户时返回 404。

### 8.2 上传

- 非 PDF、Markdown、TXT 文件拒绝上传。
- 解析失败时不写入 Chroma。
- Chroma 写入失败时文档状态标记失败，并尽量清理已写入 chunk。
- 删除文档时同步删除上传文件、SQLite 记录和 Chroma chunk。

### 8.3 选库与通用模式

- 手动选择知识库后 Agent 不覆盖。
- 无相关知识库时进入通用学习模式。
- 通用模式回答必须说明未引用用户资料。
- 有知识库但检索不到相关 chunk 时，提示未从上传资料中检索到直接相关内容。

### 8.4 模型调用失败

- LLM 失败时返回可理解错误。
- Embedding 失败时上传失败，不创建可用索引。
- 会话创建时路径生成失败，保留会话记录并允许重试。
- 聊天失败时保存用户消息，不保存失败的 assistant 消息。

### 8.5 路径和测验

- 学习路径生成失败时允许重新生成。
- Agent 调整路径时直接覆盖当前路径，并记录 `agent_events`。
- 用户手动编辑路径后，如 Agent 要覆盖，需要在界面提示。
- 简答题评分失败时可重试；如果仍失败，该题标记为未评分，不计入准确率。

## 9. 测试与验收

### 9.1 核心验收流程

```text
注册用户
-> 登录
-> 创建知识库
-> 上传 PDF/Markdown/TXT
-> 创建学习会话，只输入学习主题
-> Agent 自动选择知识库或进入通用模式
-> 生成纵向学习路径
-> 在当前阶段聊天问答
-> 回答展示来源文档名
-> 生成阶段测验
-> 前端逐题作答
-> 统一提交评分
-> 生成反馈
-> 低分时调整路径，高分时建议进入下一阶段
-> 完成阶段并生成阶段摘要
-> 手动结束会话并生成最终总结、主题、标签
-> 在用户信息页看到历史会话和学习进度
```

### 9.2 后端测试重点

- 注册、登录、退出、当前用户。
- 用户数据隔离。
- 知识库创建、编辑、删除。
- 文档上传、解析、索引、删除。
- 创建会话后生成学习路径。
- 无相关知识库时进入通用模式。
- 手动选择知识库优先于 Agent 自动选择。
- 聊天消息保存。
- RAG 返回来源文档名。
- 测验生成、提交、评分和路径调整。
- 阶段摘要和会话总结。

### 9.3 Agent 验收重点

- 自动选库必须返回选择结果和简短理由。
- 无知识库或无相关知识库时必须进入通用学习模式。
- 学习路径必须是结构化阶段列表。
- 聊天必须围绕当前阶段和学习主题回答。
- RAG 回答只展示来源文档名。
- 测验必须包含至少两类题型，理想情况包含选择题、判断题、简答题。
- 简答题必须有 LLM 评分和简短评语。
- 路径调整必须给出调整理由。
- 会话总结必须包含主题、标签、学习摘要、掌握情况、后续建议。

### 9.4 前端验收重点

- 当前学习主题。
- 当前使用知识库或通用学习模式。
- 纵向学习路径。
- 当前阶段状态和进度。
- 聊天窗口。
- 来源文档名。
- 测验入口、逐题作答、结果反馈。
- 简短 Agent 状态提示。

不验收移动端适配，不要求复杂动画，不要求知识地图真实生成。知识地图第一版只保留区域即可。

### 9.5 手动验收场景

1. 有资料学习：上传一份专业资料，创建相关主题会话，验证 Agent 选库、RAG、路径、测验和总结。
2. 无资料学习：不上传资料，直接创建学习主题，验证通用学习模式和无来源提示。
3. 知识库切换建议：创建两个知识库，在一个会话中提明显偏离当前知识库的问题，验证 Agent 只建议切换，不自动切换。

## 10. 后续扩展

以下内容不进入第一版：

- 互联网搜索。
- FAISS 检索演示。
- 后台任务队列。
- 管理员角色。
- Django 管理后台。
- 复杂长期记忆。
- 多端适配。
- 软删除和恢复。
- 知识地图自动关系图。
- 多 provider 动态切换。

