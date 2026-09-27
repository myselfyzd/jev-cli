# 第三方内容说明 / Third-party notices

## 题目集（核心资产）

`jev/questions.py` 里的 `QUESTIONS`（7 道判断题的英文 instructions 与 criteria）、
`build_state()` 的 state 结构，以及 `build_rank_question()` 的排序题措辞，
原样取自开源项目：

    332_lab-jev-chat — https://github.com/Liyucheng1997/332_lab-jev-chat
    文件：tools/jev/questions.py
    许可：MIT License
    版权：Copyright (c) 该项目作者

`fixtures/labeled_set.json`（30 条人工标注的中文对话片段）同样来自该项目的
`tools/jev/fixtures/labeled_set.json`，MIT License，未做修改。

原项目的思路（判断模型 + 生成模型 + 排序，非侵入式采集）来自同一个仓库，
许可为 MIT。本项目只保留了它的**判断层与编排原理**，去掉了 Android 采集层与 UI，
换成命令行输入输出，并补上了上游缺失的校准脚本与自动化测试。

## 模型服务

- 默认 judge / writer / ranker 走 DeepSeek 官方 API（`https://api.deepseek.com`）。
- `--judge jev` 走 TypeSafe Jev 判断模型，经 OpenRouter 的 alpha decisions 接口
  （`https://openrouter.ai/api/alpha/decisions`，模型 `typesafe/jev-1.13`）。

两个服务的密钥都由使用者自己提供，本仓库不含任何密钥。
