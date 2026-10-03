# Rename this to model.py once models/relearn-physics exists.
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

PATH = "models/relearn-physics"
tok = AutoTokenizer.from_pretrained(PATH)
net = AutoModelForSequenceClassification.from_pretrained(PATH).eval()


def diagnose(question, choice, explanation):
    correct = choice == question["correct"]
    text = f"Q: {question['text']} | Answer: {question['options'][choice]} | Explanation: {explanation or ''}"
    with torch.no_grad():
        probs = net(**tok(text, return_tensors="pt", truncation=True, max_length=256)).logits.softmax(-1)[0]
    conf, idx = probs.max(0)
    label = net.config.id2label[int(idx)]
    label = None if label == "NONE" else label
    if correct:
        status = "flawed_reasoning" if label else "correct"
    else:
        status = "misconception" if label else "unknown"
    return {"correct": correct, "status": status, "label": label, "confidence": round(float(conf), 2)}
