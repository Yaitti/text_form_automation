# Установка
```bash
git clone https://github.com/your-repo/sixmo-form-automation.git
cd sixmo-form-automation
pip install -r requirements.txt
playwright install chromium
```
# Запуск скрипта

Через аргумент командной строки:
```bash

python main.py input.json
```
Через stdin:
```bash

cat input.json | python main.py -
```

# Формат выходных данных 

При успешном завершении:
```json

{
  "success": true,
  "identifier": "8E61EA901D89",
  "result": "Прохождение завершено",
}
```

В случае ошибки:
```json

{
  "success": false,
  "error": "Описание ошибки",
}
```
