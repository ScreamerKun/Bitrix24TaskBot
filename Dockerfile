FROM python:3.10

WORKDIR /app

COPY . .

RUN pip install --upgrade pip --upgrade pip setuptools wheel --no-cache-dir -r requirements.txt

COPY . /bot
WORKDIR /bot
RUN pip install -r requirements.txt

CMD ["python", "bot.py"]
