FROM python:3.8-alpine

ADD . /app/
WORKDIR /app/
RUN pip install -r requirements.txt

USER guest
CMD ["hypercorn", "nothub", "-b", "0.0.0.0:8080"]
