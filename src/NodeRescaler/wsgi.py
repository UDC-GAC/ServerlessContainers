from werkzeug.serving import WSGIRequestHandler

from NodeRescaler import app

if __name__ == "__main__":
    WSGIRequestHandler.protocol_version = "HTTP/1.1"
    app.run(host='0.0.0.0')
