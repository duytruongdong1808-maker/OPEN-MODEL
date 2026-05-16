# Lý thuyết và cách train model trong repo OPEN-MODEL

Tài liệu này dành cho người đã biết Python cơ bản và muốn hiểu repo này đang train model như thế nào. Mục tiêu không phải là biến mọi thứ thành công thức khó đọc, mà là nối được ba lớp kiến thức:

- Ý tưởng nền: token, trọng số, loss, gradient descent.
- Cách fine-tune LLM bằng LoRA/QLoRA.
- Pipeline thật trong repo: data JSONL -> prepare data -> train LoRA adapter -> eval/chat.

Repo này mặc định dùng `Qwen/Qwen2.5-7B-Instruct` làm base model và fine-tune bằng LoRA/QLoRA. Nói ngắn gọn: ta không train một model từ số 0. Ta lấy một model đã học sẵn rất nhiều tri thức, rồi train thêm một phần adapter nhỏ để model trả lời hợp hơn với dữ liệu Gmail/chat của mình.

## 1. Model, token và trọng số là gì?

Một model machine learning là một hàm có tham số:

```text
output = model(input, weights)
```

Trong Python tưởng tượng đơn giản:

```python
prediction = x * weight + bias
```

Ở đây `weight` và `bias` là trọng số. Ban đầu chúng có thể chưa đúng. Training là quá trình chỉnh các trọng số để prediction gần đáp án mong muốn hơn.

Với language model, input không đi thẳng vào model dưới dạng chữ. Câu chữ được tách thành token:

```text
"Xin chào" -> [token_1, token_2, ...]
```

Mỗi token được đổi thành một vector số qua embedding. Model nhận các vector này, đi qua nhiều lớp neural network, rồi dự đoán token tiếp theo.

Với causal language model, mục tiêu cơ bản là:

```text
Cho các token trước đó, dự đoán token kế tiếp.
```

Ví dụ:

```text
Input:  "Hôm nay trời"
Target: "đẹp"
```

Model sinh ra xác suất cho nhiều token có thể đứng tiếp theo. Nếu xác suất của token đúng càng cao thì loss càng thấp.

## 2. Training khác inference như thế nào?

Inference là lúc model đã có trọng số và ta dùng nó để trả lời:

```text
prompt -> model -> response
```

Training là lúc ta có cặp input/đáp án đúng và dùng lỗi sai để cập nhật trọng số:

```text
prompt + expected completion -> model -> loss -> gradient -> update weights
```

Trong repo này:

- Inference local dùng `src/chat.py`, `src/eval.py`, hoặc backend trong `src/server/`.
- Training dùng `src/train_lora.py`.
- Chuẩn bị prompt/completion cho training dùng `src/prepare_data.py`.

## 3. Loss, cross-entropy và gradient descent

Loss là con số đo model đang sai bao nhiêu. Với bài toán dự đoán token, loss thường là cross-entropy.

Nếu token đúng có xác suất `p`, loss của token đó là:

```text
loss = -log(p)
```

Nếu model rất tự tin vào đáp án đúng:

```text
p = 0.90 -> loss thấp
```

Nếu model gán xác suất thấp cho đáp án đúng:

```text
p = 0.01 -> loss cao
```

Gradient descent là cách chỉnh trọng số theo hướng làm loss giảm:

```text
weight = weight - learning_rate * gradient
```

Các khái niệm hay gặp:

- `learning_rate`: bước nhảy mỗi lần cập nhật. Cao quá dễ học lệch, thấp quá học chậm.
- `batch_size`: số mẫu xử lý trong một lượt forward/backward.
- `gradient_accumulation_steps`: gom nhiều micro-batch trước khi update, giúp giả lập batch lớn khi GPU ít VRAM.
- `epoch`: một vòng đi qua toàn bộ training dataset.
- `validation loss`: loss trên tập validation, dùng để xem model có học tổng quát không.
- `warmup_ratio`: giai đoạn đầu tăng learning rate từ từ để training ổn định hơn.

Trong `configs/rtx4060ti_8gb_mail_agent.yaml`, repo dùng:

```yaml
learning_rate: 5.0e-5
per_device_train_batch_size: 1
gradient_accumulation_steps: 16
num_train_epochs: 2
warmup_ratio: 0.03
```

Nghĩa là mỗi lần GPU xử lý 1 mẫu, nhưng tích lũy gradient qua 16 lượt rồi mới update một lần.

## 4. Vì sao không train toàn bộ model?

`Qwen/Qwen2.5-7B-Instruct` có khoảng 7 tỷ tham số. Nếu cập nhật toàn bộ trọng số, ta cần rất nhiều VRAM, dữ liệu, thời gian, và rủi ro làm model quên năng lực cũ.

Repo này dùng LoRA:

```text
W_new = W_base + delta_W
```

Trong đó:

- `W_base` là trọng số gốc của base model, được giữ cố định.
- `delta_W` là phần thay đổi nhỏ được học thêm.
- LoRA biểu diễn `delta_W` bằng hai ma trận nhỏ hơn:

```text
delta_W = B @ A
```

Thay vì train toàn bộ `W_base`, ta chỉ train `A` và `B`. Vì vậy file kết quả gọi là adapter, thường nhỏ hơn nhiều so với full model.

Trong `src/train_lora.py`, LoRA được cấu hình bằng `LoraConfig`:

```python
peft_config = LoraConfig(
    r=args.lora_r,
    lora_alpha=args.lora_alpha,
    lora_dropout=args.lora_dropout,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=[
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    ],
)
```

Ý nghĩa các tham số chính:

- `lora_r`: rank của adapter. Rank cao hơn có nhiều năng lực học hơn nhưng tốn VRAM hơn.
- `lora_alpha`: hệ số scale cho adapter.
- `lora_dropout`: dropout trong adapter, giúp giảm overfit.
- `target_modules`: các lớp trong transformer sẽ được gắn LoRA.

## 5. QLoRA là gì?

QLoRA là LoRA kết hợp quantization. Base model được nạp ở 4-bit để giảm VRAM, còn adapter LoRA vẫn được train.

Trong repo:

- `load_in_4bit: true` bật QLoRA.
- `build_bnb_config()` trong `src/utils.py` dùng `BitsAndBytesConfig` với `nf4` và double quant.
- `prepare_model_for_kbit_training()` trong `src/train_lora.py` chuẩn bị model 4-bit cho training.

Điểm quan trọng:

- QLoRA giúp train model 7B trên GPU nhỏ hơn, ví dụ RTX 4060 Ti 8 GB.
- Trên Windows native, 4-bit CUDA có thể kén môi trường; README khuyến nghị WSL2/Linux cho đường train sạch nhất.
- Nếu chỉ smoke test code path mà không cần QLoRA, có thể dùng `--load_in_4bit false`, nhưng CPU/full precision sẽ rất chậm.

## 6. Pipeline dữ liệu trong repo

Repo dùng định dạng raw JSONL ban đầu:

```json
{"instruction":"Explain LoRA simply.", "input":"", "output":"LoRA trains small adapter weights instead of updating the full model."}
```

Mỗi dòng là một ví dụ training.

Luồng chính:

```text
data/raw/*.jsonl
  -> src/curate_data.py
  -> src/build_dataset.py
  -> data/curated/gmail_real_train.jsonl
  -> src/prepare_data.py
  -> data/processed/train_sft_gmail_real.jsonl
  -> src/train_lora.py
  -> outputs/.../final_adapter
```

### `curate_data.py`

Script này kiểm tra chất lượng dữ liệu:

- Có `instruction` và `output` không.
- Output quá ngắn/quá dài không.
- Dữ liệu có dấu hiệu lỗi encoding, trùng lặp, hoặc không phù hợp không.
- Gắn metadata như `task_type`, `language`, `quality_score`, `flags`, `action`.

Các dòng tốt đi vào curated train. Các dòng cần xem lại đi vào review candidates.

### `build_dataset.py`

Script này trộn các nguồn curated thành dataset cân bằng. Với profile `gmail_real_v1`, README mô tả tỉ lệ mặc định:

```text
85% Gmail-real
15% general/safety
```

Mục tiêu là không để model chỉ học một kiểu dữ liệu quá hẹp.

### `prepare_data.py`

Đây là bước rất quan trọng. Raw row có `instruction`, `input`, `output`, nhưng trainer cần format đúng chat template của base model.

`render_training_record()` trong `src/utils.py` tạo:

```json
{"prompt":"...", "completion":"..."}
```

Prompt được tạo bằng tokenizer chat template:

```python
prompt = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
)
completion = output_text + (tokenizer.eos_token or "")
```

Nói đơn giản:

- `prompt` chứa system message và user message theo format Qwen hiểu.
- `completion` là câu trả lời đúng của assistant.
- Repo lưu metadata sidecar để đảm bảo dataset được prepare bằng đúng base model.

Nếu đổi base model, phải chạy lại `prepare_data.py`, vì tokenizer/chat template có thể khác.

### `train_lora.py`

Script train làm các việc chính:

1. Đọc YAML config và CLI args.
2. Kiểm tra processed dataset tồn tại.
3. Kiểm tra metadata dataset khớp `base_model`.
4. Load tokenizer.
5. Load dataset JSONL bằng `datasets.load_dataset`.
6. Load base model, có thể ở 4-bit.
7. Gắn LoRA config.
8. Tạo `SFTTrainer`.
9. Train.
10. Lưu adapter cuối vào `final_adapter`.

Repo dùng `completion_only_loss=True`, nghĩa là trainer chỉ tính loss trên phần assistant completion, không ép model học lại prompt/user text.

Trong `src/train_lora.py`, hàm `assert_label_masking()` kiểm tra điều này bằng cách xem label mask có cả token bị mask `-100` và token completion được supervise.

## 7. Ý nghĩa config train chính

File quan trọng:

```text
configs/rtx4060ti_8gb_mail_agent.yaml
```

Các trường chính:

```yaml
base_model: Qwen/Qwen2.5-7B-Instruct
preset: rtx4060ti_8gb
dataset_path: data/processed/train_sft_gmail_real.jsonl
val_dataset_path: data/processed/val_sft_gmail_real.jsonl
output_dir: outputs/qwen2.5_7b_lora_gmail_real_v1
num_train_epochs: 2
learning_rate: 5.0e-5
per_device_train_batch_size: 1
gradient_accumulation_steps: 16
max_length: 768
lora_r: 16
lora_alpha: 32
lora_dropout: 0.05
load_in_4bit: true
gradient_checkpointing: true
warmup_ratio: 0.03
save_steps: 100
logging_steps: 10
report_to: none
```

Diễn giải:

- `base_model`: model nền từ Hugging Face.
- `dataset_path`: tập train đã xử lý thành `prompt`/`completion`.
- `val_dataset_path`: tập validation để đo eval loss.
- `output_dir`: nơi lưu checkpoint, config và adapter.
- `max_length`: số token tối đa cho prompt + completion. Tăng lên tốn VRAM hơn.
- `load_in_4bit`: bật QLoRA.
- `gradient_checkpointing`: đổi thêm compute để tiết kiệm VRAM.
- `save_steps`: mỗi bao nhiêu optimizer step thì lưu checkpoint.
- `logging_steps`: mỗi bao nhiêu step thì log.
- `report_to`: `none`, `tensorboard`, hoặc `wandb`.

## 8. Cách chạy từ đầu đến cuối

### Cài dependencies

```powershell
pip install -r requirements-dev.txt
```

Hoặc nếu chỉ chạy runtime:

```powershell
pip install -r requirements.txt
```

### Chuẩn bị data

Nếu dùng sample public:

```powershell
.\.venv\Scripts\python.exe -X utf8 src\download_sample_data.py
.\.venv\Scripts\python.exe -X utf8 src\curate_data.py
.\.venv\Scripts\python.exe -X utf8 src\build_dataset.py --target_profile gmail_real_v1
.\.venv\Scripts\python.exe -X utf8 src\prepare_data.py
```

Lệnh tối thiểu cần có trước training:

```bash
python src/prepare_data.py
```

### Smoke test train

Chạy vài step để kiểm tra môi trường, data, tokenizer và model path:

```bash
python src/train_lora.py --config configs/rtx4060ti_8gb_mail_agent.yaml --max_steps 50
```

Windows PowerShell nên dùng interpreter trong virtualenv:

```powershell
.\.venv\Scripts\python.exe -u -X utf8 src\train_lora.py --config configs\rtx4060ti_8gb_mail_agent.yaml --max_steps 50
```

### Full train

```bash
python src/train_lora.py --config configs/rtx4060ti_8gb_mail_agent.yaml
```

Kết quả chính:

```text
outputs/qwen2.5_7b_lora_gmail_real_v1/final_adapter
```

Đây là adapter LoRA, không phải toàn bộ full model.

### Eval

```bash
python src/eval.py
```

Hoặc chỉ định eval set:

```bash
python src/eval.py --eval_path data/eval/gmail_real_gold.jsonl
```

### Chat local

```bash
python src/chat.py
```

PowerShell:

```powershell
.\.venv\Scripts\python.exe -X utf8 src\chat.py
```

## 9. Đọc loss curve như thế nào?

Loss train giảm nghĩa là model đang khớp training data tốt hơn. Nhưng chỉ nhìn train loss là chưa đủ.

Các dấu hiệu thường gặp:

- Train loss giảm, validation loss giảm: tốt.
- Train loss giảm, validation loss tăng: có thể overfit.
- Loss nhảy mạnh hoặc thành `nan`: learning rate quá cao, dữ liệu lỗi, hoặc môi trường số học không ổn.
- Loss gần như không giảm: learning rate quá thấp, dữ liệu quá ít, prompt/completion format sai, hoặc adapter capacity thấp.

Repo có hình tham khảo:

```text
docs/expected-loss-curve.svg
```

## 10. Lỗi thường gặp

### Thiếu processed dataset

Lỗi kiểu:

```text
Processed dataset not found: data/processed/train_sft_gmail_real.jsonl
```

Cách xử lý:

```bash
python src/prepare_data.py
```

Nếu curated dataset chưa có, chạy lại các bước trước đó:

```bash
python src/curate_data.py
python src/build_dataset.py --target_profile gmail_real_v1
python src/prepare_data.py
```

### Base model mismatch

Nếu prepare data bằng model A nhưng train bằng model B, repo sẽ báo mismatch. Cách xử lý là chạy lại:

```bash
python src/prepare_data.py --base_model Qwen/Qwen2.5-7B-Instruct
```

Hoặc dùng đúng `base_model` trong config.

### CUDA out of memory

Giảm VRAM bằng cách:

- Giảm `max_length`, ví dụ từ `768` xuống `512`.
- Giữ `per_device_train_batch_size: 1`.
- Tăng `gradient_accumulation_steps` nếu muốn giữ effective batch size.
- Bật `load_in_4bit: true`.
- Bật `gradient_checkpointing: true`.
- Dùng model nhỏ hơn như `Qwen/Qwen2.5-3B-Instruct`.

### 4-bit không chạy được

QLoRA cần CUDA và `bitsandbytes` phù hợp. Đường ổn nhất cho repo này là WSL2/Linux với NVIDIA GPU passthrough.

Nếu chỉ muốn kiểm tra script:

```bash
python src/train_lora.py --load_in_4bit false --max_steps 1
```

Nhưng chạy CPU/full precision có thể rất chậm.

## 11. Cách nối kiến thức với code

Nếu bạn đọc từ Python cơ bản, nên đi theo thứ tự:

1. Mở notebook `docs/model-training-walkthrough-vi.ipynb` để hiểu trọng số, loss, gradient update và LoRA bằng ma trận nhỏ.
2. Đọc `src/utils.py`, đặc biệt `render_training_record()`, `load_tokenizer()`, `build_bnb_config()`.
3. Đọc `src/prepare_data.py` để hiểu data được biến thành `prompt`/`completion`.
4. Đọc `src/train_lora.py` từ `parse_args()` đến `SFTTrainer`.
5. Chạy smoke test `--max_steps 50`.
6. Chạy `src/eval.py` để xem adapter trả lời khác base model như thế nào.

Một câu tóm tắt toàn bộ repo:

```text
Repo này không tạo trí tuệ từ số 0; nó dạy một model đã biết nhiều thứ cách trả lời tốt hơn cho domain của bạn bằng cách train một adapter nhỏ, rẻ hơn và dễ thay thế hơn full model.
```
