# pip install torch transformers datasets sentencepiece accelerate
# train.csv / test.csv columns: question, answer, explanation, label  (split by question!)
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments

BASE = "microsoft/deberta-v3-base"
OUT = "models/relearn-physics"

ds = load_dataset("csv", data_files={"train": "train.csv", "test": "test.csv"})
labels = sorted(set(ds["train"]["label"]))
l2i = {l: i for i, l in enumerate(labels)}
tok = AutoTokenizer.from_pretrained(BASE)


def fmt(q, a, e):  # must match the format in model_trained.py
    return f"Q: {q} | Answer: {a} | Explanation: {e or ''}"


def prep(b):
    enc = tok([fmt(q, a, e) for q, a, e in zip(b["question"], b["answer"], b["explanation"])],
              truncation=True, max_length=256)
    enc["labels"] = [l2i[l] for l in b["label"]]
    return enc


ds = ds.map(prep, batched=True)
model = AutoModelForSequenceClassification.from_pretrained(
    BASE, num_labels=len(labels), id2label=dict(enumerate(labels)), label2id=l2i)

Trainer(model=model, tokenizer=tok, train_dataset=ds["train"], eval_dataset=ds["test"],
        args=TrainingArguments("out", num_train_epochs=4, per_device_train_batch_size=8,
                               learning_rate=2e-5)).train()

model.save_pretrained(OUT)
tok.save_pretrained(OUT)
print("Saved to", OUT)
