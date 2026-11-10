FROM ubuntu:22.04
WORKDIR /app
COPY . .
RUN apt update && apt install python3.10 python3-pip -y
RUN pip3 install flask requests crate
EXPOSE 80
CMD ["python3", "app.py"]
