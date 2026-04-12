# WAN 2.2 自动化工作流技术文档 (v2.1 - Dynamic Placeholder Pattern)

本手册记录了 `nsfw_ui.py` 中 WAN 2.2 多步骤生成流水线的完整系统架构。**v2.1 版本引入了 `**XXX**` 占位符模式，简化了动态工作流生成逻辑。**

---

## 1. 核心任务架构 (Flat Jobs Architecture)

系统采用扁平化的 Job 架构，不再以"UI 行"为单位处理任务，而是将任务打散为独立的 **Job**。

### 1.1 Job ID 生成
- **唯一 Job ID**: 每个 Job 分配一个由 8 位随机字符组成的 `job_id`（例如：`h1k8ba`）
- **生成方式**: 使用 `generate_random_string(8)` 函数生成

### 1.2 Batch 处理
- 若 Batch 数量大于 1，系统会为每个 Batch 创建独立的 Job
- 每个 Job 复制一份源图像到 `input/` 文件夹，命名为 `{job_id}.png`

### 1.3 顺序执行流
```
发送 Job N → 等待完成 → 发现并记录输出文件 → 发送 Job N+1
```

---

## 2. 动态工作流生成 (`**XXX**` 占位符模式)

**v2.1 核心变更**: 采用 `**XXX**` 占位符直接放在 workflow JSON 的 input values 中，通过字符串匹配和替换实现动态参数注入。

### 2.1 占位符命名规范
- **格式**: `**placeholder_name**` (双星号开头和结尾)
- **位置**: 放在 workflow JSON 节点的 `inputs` 字段值中（必须是字符串类型）
- **识别**: 代码遍历所有 input values，查找包含 `**XXX**` 的字符串

### 2.2 占位符映射表

| 占位符 | 替换值 | 适用步骤 | 说明 |
|--------|--------|----------|------|
| `**width**` | `row["side"]` | step0 | 视频宽度 (side=width) |
| `**second**` | `row["seconds"]` | step0 | 视频时长 (秒) |
| `**prompt**` | `vp or row["video_prompt"]` | step0 | 视频提示词 |
| `**audio_prompt**` | `ap or row["audio_prompt"]` | step0 | 音频提示词 |
| `**pos_conditioning**` | `discovered pos filename` | step1,2 | 正 conditioning 文件 |
| `**neg_conditioning**` | `discovered neg filename` | step1,2 | 负 conditioning 文件 |
| `**latent_input**` | `discovered latent filename` | step1,2,3 | 上一步的 latent |
| `**latent_output**` | `lat_{jid}_s{step_idx}` | step1,2 | 本步输出的 latent |
| `**video_output**` | `video/{jid}` | step3 | 最终视频输出 |
| `**row_id_in**` | `{jid}` | FlashSVR | 输入视频 |
| `**row_id_out**` | `{jid}_upscaled` | FlashSVR | 输出视频 |
| `**finish_indicator**` | `{jid}` | clean_up | 完成标记文件 |

### 2.3 字符串替换逻辑
```python
for k, v in inputs.items():
    if isinstance(v, str):
        if "**width**" in v:
            inputs[k] = int(row["side"]) if cls == "JWInteger" else row["side"]
        elif "**second**" in v:
            inputs[k] = int(row["seconds"]) if cls == "JWInteger" else row["seconds"]
        elif "**prompt**" in v:
            inputs[k] = vp if vp else row["video_prompt"]
        elif "**pos_conditioning**" in v:
            inputs[k] = job_files.get("pos", f"pos_{jid}.pt")
        # ... 其他占位符
```

### 2.4 类型转换处理
- **整数字段**: 对于 `JWInteger` class_type，自动将字符串转换为 int
- **字符串字段**: 直接替换为对应的字符串值
- **路径字段**: 保持 `latents\\` 或 `video\\` 前缀

---

## 3. 工作流模板占位符分布

### 3.1 wan_2.2_step0.json
| Node ID | Input Field | 占位符 | 说明 |
|---------|-------------|--------|------|
| 3 | value | `**width**` | 视频宽度 (从 side) |
| 18 | value | `**second**` | 视频时长 (从 seconds) |
| 54 | text | `**prompt**` | 视频提示词 |

### 3.2 wan_2.2_step1.json
| Node ID | Input Field | 占位符 | 说明 |
|---------|-------------|--------|------|
| 12 | conditioning_file | `**pos_conditioning**` | 加载正 conditioning |
| 13 | conditioning_file | `**neg_conditioning**` | 加载负 conditioning |
| 15 | filename_prefix | `latents/**latent_output**` | 保存 latent 输出 |
| 29 | latent | `latents\**latent_input**` | 加载 step0 latent |

### 3.3 wan_2.2_step2.json
| Node ID | Input Field | 占位符 | 说明 |
|---------|-------------|--------|------|
| 12 | conditioning_file | `**pos_conditioning**` | 加载正 conditioning |
| 13 | conditioning_file | `**neg_conditioning**` | 加载负 conditioning |
| 15 | filename_prefix | `latents/**latent_output**` | 保存 latent 输出 |
| 18 | latent | `latents\**latent_input**` | 加载 step1 latent |

### 3.4 wan_2.2_step3.json
| Node ID | Input Field | 占位符 | 说明 |
|---------|-------------|--------|------|
| 6 | filename_prefix | `video/**video_output**` | 保存最终视频 |
| 7 | latent | `latents\**latent_input**` | 加载 step2 latent |

### 3.5 FlashSVR.json
| Node ID | Input Field | 占位符 | 说明 |
|---------|-------------|--------|------|
| 19 | filename_prefix | `video/**row_id_out**` | 保存超分视频 |
| 20 | video | `ComfyUI/output/video/**row_id_in**.mp4` | 加载输入视频 |

### 3.6 final_upscale.json
| Node ID | Input Field | 占位符 | 说明 |
|---------|-------------|--------|------|
| 8 | filename_prefix | `video/**row_id_out**` | 保存超分视频 |
| 15 | video | `ComfyUI/output/video/**row_id_in**.mp4` | 加载输入视频 |

### 3.7 clean_up.json
| Node ID | Input Field | 占位符 | 说明 |
|---------|-------------|--------|------|
| 4 | file | `**finish_indicator**.txt` | 完成标记文件 |

---

## 4. 文件命名与步骤区分

### 4.1 Conditioning 文件
- **命名格式**: `pos_{jid}.pt` 和 `neg_{jid}.pt`
- **输出位置**: `output/conditionings/`

### 4.2 Latent 文件
- **命名格式**: `lat_{jid}_s{N}_00001_.latent`
  - `{jid}`: Job ID (8 位随机字符串)
  - `{N}`: 步骤索引 (0, 1, 2)
- **输出位置**: `output/latents/`

### 4.3 输出视频文件
- **命名格式**: `{jid}_*.mp4`
- **超分视频**: `{jid}_upscaled_*.mp4`
- **位置**: `output/video/`

---

## 5. 发现与记录逻辑 (Discovery & Tracking)

每一步执行成功后，UI 扫描输出目录并将文件名记录到 `discovered_outputs` 字典：

```python
# 扫描 conditioning 文件
for p in [f"pos_{jid}", f"neg_{jid}"]:
    fname = f"{p}.pt"
    if os.path.exists(src):
        self.discovered_outputs[jid]["pos" if "pos" in p else "neg"] = fname

# 扫描 latent 文件
cur_p = f"lat_{jid}_s{step_idx}"
matches = [f for f in l_files if f.startswith(cur_p) and f.endswith(".latent")]
if matches:
    self.discovered_outputs[jid]["lat"] = max(matches, key=...)
```

---

## 6. 工作流步骤详解 (task_steps.csv)

| 步骤 | Workflow | Save Video | 说明 |
|------|----------|------------|------|
| 1 | audio_nsfw | yes | 音频生成 (可选) |
| 2 | wan_2.2_step0 | no | 图像→Conditioning + Latent |
| 3 | wan_2.2_step1 | no | Conditioning + Latent → Latent |
| 4 | wan_2.2_step2 | no | Conditioning + Latent → Latent |
| 5 | wan_2.2_step3 | yes | Latent → Video |
| 6 | FlashSVR | yes | Video → Upscaled Video (可选) |

---

## 7. 修改工作流模板指南

### 7.1 添加新的占位符

**Step 1**: 在 workflow JSON 的 input field 中添加占位符:
```json
"inputs": {
  "some_field": "**my_placeholder**"
}
```

**Step 2**: 在 `nsfw_ui.py` 的占位符处理逻辑中添加映射:
```python
elif "**my_placeholder**" in v:
    inputs[k] = row["my_field"]  # 或 job_files.get("key")
```

**Step 3**: 更新 `workflow_params.csv` 文档:
```
wan_2.2_step0,**my_placeholder**,description of what it maps to
```

### 7.2 整数类型占位符

对于整数类型的 input field，将占位符作为字符串写入，代码会自动转换:
```json
"inputs": {
  "value": "**width**"  // 字符串形式
}
```
代码处理:
```python
if "**width**" in v:
    inputs[k] = int(row["side"]) if cls == "JWInteger" else row["side"]
```

---

## 8. 调试方法

### 8.1 Debug Workflows
检查 `debug_workflows/` 文件夹下的生成的 JSON 文件，查看占位符是否被正确替换:
```
{jid}_step{step_idx}_{wf_name}.json
```

### 8.2 验证替换结果
生成的 JSON 中不应再包含 `**XXX**` 占位符，应被实际值替换:
- `**width**` → `720` (或实际 side 值)
- `**prompt**` → `"actual prompt text"`
- `**pos_conditioning**` → `"pos_h1k8ba.pt"`

### 8.3 检查日志
```
--- Step 1/5: 'wan_2.2_step0' ---
DEBUG: Processing job h1k8ba...
```

---

## 9. 故障排查

### 9.1 占位符未被替换
- 检查占位符格式是否为 `**XXX**` (双星号开头和结尾)
- 确认占位符放在 input values 中，而非 `_meta.title`
- 检查代码中是否有对应的处理逻辑

### 9.2 类型转换错误
- 整数字段确保使用 `int()` 转换
- 检查 class_type 判断条件 (`if cls == "JWInteger"`)

### 9.3 文件路径错误
- 路径分隔符使用 `\\` (代码中) 或 `/` (JSON 中)
- 确认路径前缀正确 (`latents\\`, `video\\`, `conditionings\\`)

---

*文档版本：2.1 | 最后更新：2026-04-12 | 对应代码：nsfw_ui.py*

**关键变更**: v2.1 从 class_type-based 识别改为 `**XXX**` 占位符模式，简化了节点识别和参数注入逻辑。