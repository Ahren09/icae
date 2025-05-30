import json
import transformers
from peft import (
    LoraConfig,
)
from datasets import load_dataset, Dataset
from modeling_icae_multi_span import ICAE, ModelArguments, DataArguments, TrainingArguments
from training_utils import pretrain_tokenize_function, DataCollatorForDynamicPadding, train_model

class WrappedDataset:
    def __init__(self, dataset):
        self.dataset = dataset

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, index):
        return self.dataset[index]

def main():
    parser = transformers.HfArgumentParser((ModelArguments, DataArguments, TrainingArguments))
    model_args, data_args, training_args = parser.parse_args_into_dataclasses()

    print(model_args)
    print(data_args)
    
    training_args.gradient_checkpointing_kwargs = {"use_reentrant": False}  # manually add this argument in the code

    lora_config = LoraConfig(
        r=model_args.lora_r,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )
    
    # check model_args.mem_size and min_tokens_for_lm
    assert (training_args.fixed_mem_size & (training_args.fixed_mem_size - 1)) == 0, "training_args.fixed_mem_size must be a power of 2"    
    assert training_args.leave_tokens_for_lm <= training_args.min_tokens_for_lm, "leave_tokens_for_lm should be fewer than min_tokens_for_lm"

    
    memory_size = training_args.fixed_mem_size

    train_file = "/workingdir/yjin328/data/RAG/pwc/PwC_train.jsonl"
    eval_file = "/workingdir/yjin328/data/RAG/pwc/PwC_test.jsonl"

    print("Loading dataset...")

    # with open(train_file, "r") as f:
    #     lines = f.readlines()
    #     print("Number of training examples:", len(lines))
    with open(eval_file, "r") as f:
        lines = f.readlines()
        lines = [json.loads(line) for line in lines]
        
        # Ahren: This is for debugging
        lines = lines[:512]
        print("Number of eval examples:", len(lines))

    # Load data into a Dataset object
    train_dataset = Dataset.from_list(lines[:512])
    eval_dataset = Dataset.from_list(lines[512:768])


    # dataset = load_dataset("json", data_files={"train": train_file, "eval": eval_file}, streaming=True) # streaming can be removed if the dataset is not very large.
    # train_dataset = dataset["train"]
    # eval_dataset = dataset["eval"]

    model = ICAE(model_args, training_args, lora_config)
    MEM_TOKENS = list(range(model.vocab_size, model.vocab_size + memory_size))

    train_dataset = train_dataset.map(pretrain_tokenize_function, batched=True, batch_size=64, fn_kwargs={"model": model, "mem": MEM_TOKENS, "lm_ratio": training_args.lm_ratio})
    eval_dataset = eval_dataset.map(pretrain_tokenize_function, batched=True, fn_kwargs={"model": model, "mem": MEM_TOKENS})   # don't add lm in the dev set.

    data_collator = DataCollatorForDynamicPadding(model.pad_token_id)
    train_model(model, train_dataset, eval_dataset, training_args, data_collator)

main()