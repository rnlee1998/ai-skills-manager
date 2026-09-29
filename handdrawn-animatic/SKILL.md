---
name: handdrawn-animatic
description: 把分镜脚本变成可播放的"动态分镜"短片（动态分镜/animatic）。用 AI 生成统一画风关键帧，再用 Python 做亚像素级慢推/侧移运镜、叠化转场、纸张颗粒与字幕，自合成钢琴 BGM，最后 ffmpeg 输出成片。适用于 Paperman 纸人手绘风、绘本风、极简插画风等"一帧一张图 + 慢运镜"的创意短片。当用户提供分镜剧本/故事板要求做 30-120 秒短片、但不想为整段跑 AI 视频（成本高、画风难控）时使用。
agent_created: true
---

# 手绘风动态分镜短片（Animatic）制作流程

## 适用判断

用这个流程当：
- 用户给了分镜剧本 / 故事板 / 镜头表，要"做成短片"
- 画风是固定统一的手绘/插画风（Paperman、绘本、极简线稿）
- 用户在意画风可控性和成本，不希望整段跑 AI 视频

不要用这个流程当：用户明确要求"真动画/人物要动起来"——那就得走图生视频，成本高一个数量级，提前告知积分消耗并让用户选。

## 成本告知（必做）

动手前必须告知：
- 图像生成每张约 5–10 积分
- 视频生成每 5 秒约 50–100 积分

60 秒全 AI 真视频 ≈ 600–1200 积分；本流程（8 张定帧 + 自制运镜）≈ 50–70 积分。

## 流程

### 1. 锁定画风基底提示词
写一段跨所有镜头完全一致的 style block（英文更稳），包含：媒介、线条质感、色彩体系（大面积黑白灰 + 极少量指定点缀色）、纸质颗粒、人物造型规范（扁平、无五官、靠肢体传情）、构图比例、排除项（no text, no watermark）。

每个镜头提示词 = style block + `SCENE: <该镜头内容>`。

固定角色/道具在每个 SCENE 里用**逐字相同**的描述重复一遍。

### 2. 生成关键帧（关键：必须串行）
```
生成一张 -> 立即重命名 -> 再生成下一张
```
**不要并行调用图像生成工具。** 文件名按秒级时间戳生成，同秒并行会互相覆盖，图会丢。踩过这个坑。

镜头数建议：60 秒 → 8 帧（比"5 段剧本"多 2–3 个呼吸镜头，节奏更顺）。

### 3. 处理水印
生成的图右下角通常带 "AI生成 ..." 水印。裁掉底部约 120–130px。
例：1080×1920 → 裁成 1080×1796，再按目标比例 aspect-fill（9:16 时左右各裁约 34px），缩放失真可忽略。

### 4. 合成 BGM（省积分）
用 numpy 自己合成，不要去买/调音频接口：
- 单音：加性谐波（7 个泛音，幅度递减）+ 每个泛音独立指数衰减 + 非谐性 + `1-exp(-t*k)` 软起音
- 混响：生成指数衰减噪声做 IR，用 `np.fft.rfft` 手写 FFT 卷积（不依赖 scipy）
- 和弦进行：慢速（64BPM）、每 3.75s 一个和弦、8 个和弦循环；写一段 15 行左右的 MIDI 音高表当稀疏主旋律
- 环境音：带通噪声（差分 + 滑动平均）+ 慢速 LFO 起伏，音量压到 0.03 左右
- 包络：3s 淡入、结尾前 7s 淡出、最后 1s 静音（配合"留白卡点"）

### 5. 运镜合成（核心）
**用 PIL 的 `Image.transform(AFFINE, BICUBIC)` 做亚像素级 Ken Burns，不要用 ffmpeg 的 zoompan**——zoompan 有整数取整导致的阶梯抖动。

做法：
```
master = 关键帧裁水印后 resize 到 (1.2*W, 1.2*H)   # 留出运镜余量
每帧: 由关键帧列表插值出 (zoom, cx, cy)
      窗宽 = MH*(W/H)/zoom, 窗高 = MH/zoom
      x0 = cx*MW - 窗宽/2 + 手持晃动, 同理 y0, 再 clamp
      out = master.transform((W,H), AFFINE, (窗宽/W,0,x0, 0,窗高/H,y0), BICUBIC)
```
要点：
- 每个段落给 2–3 个**运镜关键帧** `(u, zoom, cx, cy)`，u 用 smoothstep 插值
- 手持微晃用**全局时间**的正弦叠加（不在段落内重置），这样切点处相机连续、不跳
- 运镜关键帧列表支持"先推后侧移"，避免长镜头单图呆板
- 叠化：段间 0.6–0.8s 交叉淡化，总长 = Σ段时长 − (段数−1)×叠化

### 6. 后期叠加
- 暖调 + 纸张纹理 + 暗角**合成成一个静态系数数组**，逐帧只做一次乘法（性能关键）
- 动态胶片颗粒池预生成 12–16 张循环使用
- **颗粒强度必须 ≤ ±2（8bit），否则码率爆炸**：±4 + CRF17 → 60s 竖屏 240MB；±2 + CRF21 → 58MB，观感几乎无差别

### 7. 字幕
用 PIL 绘制，**不要用 ffmpeg drawtext**（中文转义极麻烦）：
- 预渲染每个字幕块为 RGBA 贴片（先画深色文字 + GaussianBlur 做柔和投影，再叠白色文字）
- 逐帧按时间轴算 alpha 贴上去
- 字体：`C:\Windows\Fonts\msyh.ttc`
- 竖屏字幕基准线放在 y≈1420/1920（下三分之一，避开平台底部 UI）

### 8. 编码
```
ffmpeg -f rawvideo -pixel_format rgb24 -video_size WxH -framerate 30 -i - \
       -i bgm.wav -filter_complex "[1:a]volume=3.2dB,alimiter=limit=0.95[a]" \
       -map 0:v -map "[a]" -c:v libx264 -preset medium -crf 21 \
       -pix_fmt yuv420p -profile:v high -level 4.1 -g 60 -movflags +faststart \
       -c:a aac -b:a 192k -ar 44100 -t <时长> out.mp4
```
Python 用 `subprocess.Popen(stdin=PIPE)` 逐帧写 rawvideo，**避免落 GB 级中间帧文件**。

## 环境要点（Windows）
- ffmpeg：`pip install imageio-ffmpeg`，用 `imageio_ffmpeg.get_ffmpeg_exe()` 拿路径（只有 ffmpeg，没有 ffprobe；看参数用 `ffmpeg -i file` 读 stderr）
- 先 `pip install numpy Pillow imageio-ffmpeg`
- **PowerShell 工具默认 120s 超时会杀掉长渲染**，即使 `run_in_background=true`。必须显式传 `timeout`（上限 600000ms）
- PowerShell stdout 不回显：让脚本自己写日志文件，再用 Read 读
- 渲染性能参考：1080×1920、1800 帧（60s@30fps），约 140ms/帧 → 总耗时 4.5 分钟

## 交付
- 成片 mp4
- 分镜册 HTML（缩略图 base64 内联，含运镜参数、字幕时间轴、可复用提示词、音频设计）
- 关键帧 PNG（供后续延展系列）

## 验收清单
- [ ] 时长精确（`Duration: 00:01:00.00`）
- [ ] 分辨率/帧率正确
- [ ] 音频流存在且为立体声
- [ ] 文件体积合理（60s 竖屏建议 30–80MB）
- [ ] 抽 3–5 帧确认无水印、无色彩偏移、字幕可读
