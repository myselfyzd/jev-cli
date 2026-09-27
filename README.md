# jev-cli — 聊天回复决策辅助（命令行版）

把一段聊天记录粘进来，它给你**结构化判断 + 3 条候选回复 + 排序**：

```
   真实意图  确认你是否在乎
   危险等级  █████░░░░░  4.0/9  阴阳怪气/试探
   对方需要  被重视
   最佳动作  先查聊天记录
   提示      先别给实质内容（别硬答） · 紧张未解除 · 话里有话
```

**边界先说明白：** 它只读你贴进来的对话，不接管任何聊天软件、不读你的账号、不联你的微信；
不自动发送，也不替你回。发送与否、发什么，你自己定。

---

## 1. 它怎么工作

三段式，判断和生成严格分工：

```
你粘贴的对话（最近 10 条 + 关系描述）
        │
        ▼
① judge      7 道结构化判断题，一次请求全发
   literal_question  noul   对方最新消息是字面意思还是话里有话
   true_intent       choice 真实意图（6 类）
   danger_level      score  离吵架/伤感情多近（10 档，每档写具体情景）
   should_reply_now  noul   下一条消息该不该含实质内容
   best_action       choice 下一步动作类型（7 类）
   she_needs         choice 对方现在要什么（5 类）
   tension_resolved  noul   紧张是否已解除
        │  （判断结果既展示给人看，也当约束喂给下一步）
        ▼
② draft      生成模型起草恰好 3 条候选，禁止自己做判断
        │
        ▼
③ rank       再让 judge 给这 3 条排序，选最该发的一条
        │
        ▼
终端展示 → /copy 复制到剪贴板（你自己粘到聊天窗口里）
```

关键点：**judge 只答选择题/打分/是非，永远不写正文**；writer 只按 judge 的结论填字，
系统提示里明确写了"你不做判断"。这是上游项目验证过的分工——判断和生成混在一个模型里，
模型会一边写一边改判断，输出不稳定。

## 2. 与上游项目的关系

判断层的题目措辞、state 结构、标注集，全部来自开源项目
[332_lab-jev-chat](https://github.com/Liyucheng1997/332_lab-jev-chat)（MIT，见 `NOTICE.md`）。

| | 上游（Android/Windows App） | 本项目 |
|---|---|---|
| 采集 | 无障碍读屏（伪装服务绕过微信节点混淆）、桌面版 UI Automation、OCR | **没有**，你自己粘贴或者从剪贴板读 |
| 判断题目 | 7 题 + 1 排序题，英文 criteria | **原样保留**（`jev/questions.py`） |
| judge 后端 | TypeSafe Jev（OpenRouter alpha decisions） | 默认换成通用模型（DeepSeek），`--judge jev` 可切回原版 |
| 校准 | 有脚本，但结果被 gitignore，仓库里查不到数字 | **补上了**，见第 6 节，带真实数字 |
| 测试 | 无 | 56 个离线单测（假后端，不花钱） |
| 分发 | 编译好的 APK 进仓库 | 单仓库纯 Python，无依赖 |

上游真正的资产是"怎么问"——那 7 道题的英文措辞踩过坑（详见 `jev/questions.py` 顶部注释）：
`should_reply_now` 和 `best_action` 会互相打架、对方明明已经收尾却判成"还要行动"，
这些都是靠改措辞压下去的。**换上任何模型都要带着这堆 criteria 走，别自己重写。**

## 3. 环境要求

- Python **3.9+**（本机系统 `python3` 是 3.6，`bin/jev` 会自动挑 `python3.12/3.11` 或 `~/.local/bin/python3.11`）
- **零第三方依赖**，纯标准库（urllib / json / argparse / unittest）
- 一个 DeepSeek API key：`export DEEPSEEK_API_KEY=sk-...`
  没设的话会去读本机已有的 `~/chat_tool/config.json`（`api.api_key` 字段）
- 只有 `--judge jev` 才需要 `OPENROUTER_API_KEY`（Jev 走 OpenRouter 的 alpha 接口）

## 4. 安装

```bash
cd ~/jev-cli
./install.sh              # 软链到 ~/.local/bin/jev，并自检 + 跑测试
```

不想装也行，直接 `./bin/jev ...`；想当包用就 `pip install -e .`。
密钥都不进配置文件和 git，只从环境变量读。

## 5. 用法

```bash
jev                              # 交互模式（stdin 是终端时）
cat chat.txt | jev               # 从管道读
jev analyze chat.txt -r 情侣      # 读文件；关系描述直接影响判断结果
jev --clip -r 同事                # 从剪贴板读对话
jev -j jev -r 情侣               # 判断层换成 TypeSafe Jev 原版
jev --judge-only                 # 只要判断，不生成候选（最省）
jev --no-rank                    # 生成 3 条，但不让 judge 排序
jev --json                       # 只输出 JSON，方便接别的脚本
jev logs -n 10                   # 看历史分析
jev show latest                  # 回看某次分析的完整结果
jev config show                  # 看当前配置和 key 状态
jev config set relationship 同事   # 改配置（会写 ~/.config/jev-cli/config.json）
jev calibrate --limit 5          # 先跑 5 条标注看校准对不对
```

真实输出（`jev analyze demos/meme.txt -r 情侣`，judge=deepseek，全程约 2.7 秒）：

```
▍结构化判断  关系：情侣  耗时 0.8s
  真实意图   确认你是否在乎
  危险等级   █████░░░░░  4.0/9  阴阳怪气/试探
  对方需要   被重视
  最佳动作   先查聊天记录
  提示       先别给实质内容（别硬答） · 紧张未解除 · 话里有话
  理由       对方用“你最好是”在测试我是否真的记得，内容未给出，需先回想而非编造。

▍候选回复 耗时 1.1s + 排序 0.8s
  ✔ 1. 我这就去翻一下咱们的聊天记录，确认好了马上跟你说，不想瞎蒙你。
    2. 你这一句“你最好是”让我有点慌，先别急，我认真回想一下，不糊弄你。
    3. 不用等了，你直接告诉我是什么事吧，我想马上确认，不想让你觉得我不在乎。

  → 建议发第 1 条  最佳动作是先查聊天记录，候选1明确说去核实而非假装记得，最符合要求。

  tokens_in=2782 tokens_out=200  (判断 0.8s + 生成 1.1s + 排序 0.8s)
```

### 交互模式命令

| 命令 | 作用 |
|---|---|
| `/go` | 分析当前缓冲（直接回车也行） |
| `/rel <关系>` | 改关系描述，会影响判断结果 |
| `/list` `/del` `/clear` | 看缓冲 / 删最后一条 / 清空 |
| `/paste` | 把剪贴板里的对话追加进来 |
| `/copy [N]` | 把第 N 条候选复制到剪贴板（默认复制排序第一那条） |
| `/json` | 打印上一次分析的 JSON |
| `/q` | 退出 |

输入一行一条消息：`对方: xxx` / `我: xxx`；不带前缀按对方算。

### 输入格式

```
对方: 你今天是不是又忘了我跟你说过什么？
我: 记得，你先别提示我，让我自己说。
你今天是不是又忘了我跟你说过什么？          # 不带前缀 = 对方
```

行首 8 个字符内有 `:` 或 `：` 才当说话人前缀，正文里的冒号不会被误切。

## 6. 校准（这个项目最该看的一节）

判断准不准不能靠感觉。`jev calibrate` 会拿标注集跑一遍 judge，
算出每题命中率和 `danger_level` 的平均绝对误差，并写报告到 `report/`。

门禁沿用上游验收口径：`danger_level` MAE < 1.0 档、`true_intent` 和 `she_needs` 命中率 ≥ 60%。

**实测结果**（2026-09-27，`judge=deepseek`，30 条上游标注集 `fixtures/labeled_set.json`，命令 `jev calibrate`）：

```
question                 hit      mae  avg_conf    n
----------------------------------------------------
literal_question       63.3%        -         -   30
true_intent            80.0%        -         -   30
danger_level           63.3%    0.400         -   30
should_reply_now       63.3%        -         -   30
best_action            80.0%        -         -   30
she_needs              76.7%        -         -   30
tension_resolved       93.3%        -         -   30
----------------------------------------------------
n=30  ok=30  errors=0  avg_latency=0.895s  tokens_in=63374  tokens_out=2810
gates: danger_mae<1.0=True  true_intent>=60%=True  she_needs>=60%=True
```

三条门禁全过。整轮 30 次请求 32.9 秒、HTTP 全 200。

`avg_conf` 是空的，因为置信度只有 Jev 会返回；通用模型 judge 不回这个字段（`--judge jev` 时才有值）。

**错得最多的地方**（校准报告 `report/calibration.md` 里有逐条差异）：

- `danger_level` 错 11/30，但方向是双向的（偏低 6 条、偏高 5 条），MAE 0.400 说明只是差一档；
  典型是"小事被当成没事"：标注 2 分判成 1 分。
- `literal_question` / `should_reply_now` 各错 11/30：
  模型偏保守，常把"对方要具体东西"判成"先别给实质内容"；
  反例是把已经收尾的对话（标注 `close_topic` / `say_less`）判成 `casual_chat` / `make_plan`。
- `tension_resolved` 最稳（93.3%），`true_intent` 和 `best_action` 都在 80%，够用。

这些偏差跟上游任务书里记的老问题同源，所以**换成自己的真实对话做校准才有意义**：

```bash
cp fixtures/labeled_set.json fixtures/my_set.json
# 按同样格式往里加你自己的对话片段，expect 里只写你有把握的那几题
jev config set fixtures ~/jev-cli/fixtures/my_set.json
jev calibrate
```

### 调试：看每一步的原始请求/响应

想知道它到底发了什么、模型回了什么，开一个抓包目录就行（Authorization 头会自动脱敏）：

```bash
JEV_TRACE_DIR=/tmp/trace jev analyze chat.txt -r 情侣
ls /tmp/trace
# 01-judge.json  02-draft.json  03-rank.json
```

每个文件里是 `{"step":1,"label":"judge","url":"...","request":{"headers":{...},"body":{...}},"response":{...}}`，
其中 `request.body.messages` 就是完整 prompt，`response.usage` 是这次消耗的 token。

## 7. 记录与回看

每次分析都会在 `logs/` 落一份 JSON（对话、判断、候选、排序、耗时、token），
用 `jev logs` 列表、`jev show latest` 回看。攒够带期望值的样本就能直接拿去做校准集。

## 8. 目录结构

```
jev-cli/
├── bin/jev               启动器（自动挑 3.9+ 的 python）
├── install.sh            软链到 ~/.local/bin/jev
├── pyproject.toml        可选打包（console script: jev）
├── jev/
│   ├── cli.py            命令行入口：子命令 + 交互模式
│   ├── questions.py      ★ 题目集（上游资产，改之前先读顶部注释）
│   ├── backends.py       judge / writer / ranker 三种后端 + 切换
│   ├── pipeline.py       三段式编排（可注入假后端，便于测试）
│   ├── llm.py            HTTP（重试、错误人话化、密钥脱敏）
│   ├── model.py          Message / Judgment / AnalysisResult / Usage
│   ├── input_parser.py   贴进来的文本 -> Message 列表
│   ├── calibrate.py      校准：命中率 / MAE / 门禁 / 报告
│   ├── render.py         终端渲染（颜色、危险等级条）
│   ├── store.py          logs/ 读写
│   ├── clipboard.py      剪贴板（xclip/xsel/wl-copy/clip.exe）
│   ├── config.py         配置与密钥解析
│   └── labels.py         中文展示标签
├── demos/                几段示例对话
├── fixtures/             标注集（30 条，来自上游，MIT）
├── tests/                56 个离线单测
└── report/               calibrate 生成的报告（不入库）
```

## 9. 测试

```bash
python3.11 -m unittest discover -s tests -t .      # 56 passed
```

全部用假后端，不打网络、不花钱。覆盖：题目集口径、输入解析、三段式编排、
usage 累加、校准命中率与门禁逻辑、报告生成、渲染、配置与子命令。

## 10. 已知限制 / 没做的

- **没有采集层**。上游用无障碍/OCR 自动读屏，这里是你手动粘贴——这是功能取舍，不是遗漏。
  真要自动化，路子是桌面版微信的 UI Automation 或轮询剪贴板，是另一个工程。
- **群聊不准**。判断口径针对一对一，"对方"和关系描述在群里失效。
- **`--judge jev` 这条路径没验证过**。本机没有 OPENROUTER_API_KEY，代码写了但一次没跑过；
  另外上游 Windows 版打的是 `api.typesafe.ai/v1/systemone`，与这里的 OpenRouter alpha 接口不一致。
- **中文判断用英文题目**。这是上游的结论（模型主训练语言是英文，中文题目效果更差），
  聊天内容保留中文原文。
- **没有"查聊天记录"能力**。`best_action=check_history` 只是提示你该去翻记录，
  工具本身没有历史库，也不会假装记得。
- 单模型 judge 不返回置信度（只有 Jev 有），所以校准表里 `avg_conf` 是空的。

## 11. 常见问题

**`没有 DeepSeek key`** — `export DEEPSEEK_API_KEY=sk-...`，或者 `jev config show` 看它有没有读到
`~/chat_tool/config.json`。

**`需要 Python 3.9+`** — 系统的 `python3` 太旧。用 `./bin/jev`（会自动挑），或
`python3.11 -m jev`。

**输出没有颜色** — 管道/重定向时自动关色；想强制关就 `--no-color` 或 `NO_COLOR=1`。

**`/copy` 说没找到剪贴板工具** — 装 `xclip`/`xsel`，或者手动选中复制输出里的候选。

**判断结果和你的直觉不一致** — 先改 `-r` 关系描述（它直接影响判断），
再考虑按第 6 节用自己的对话做一个小标注集量化一下；不要凭单个案例改 `questions.py` 的措辞。

## 12. 许可与致谢

- 本项目 MIT（`LICENSE`）。
- 题目集、state 结构、标注集来自 [332_lab-jev-chat](https://github.com/Liyucheng1997/332_lab-jev-chat)（MIT），
  见 `NOTICE.md` 与 `THIRD_PARTY_LICENSE_upstream_MIT.txt`。
- 判断模型的原始方案来自 [TypeSafe Jev](https://typesafe.ai/)。
- 仅供个人学习与研究；只处理你自己设备上、你自己有权查看的对话。
