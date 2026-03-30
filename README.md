# Change this repo to deeplint dev

### Start:

```
python3 src/repoaudit.py \
  --scan-type dfbscan \
  --project-path /path/to/your/project \
  --language Cpp \
  --bug-type UAF \
  --model-name <your-model-name> \
  --temperature 0.5 \
  --call-depth 3 \
  --max-neural-workers 8 \
  --max-symbolic-workers 30
```