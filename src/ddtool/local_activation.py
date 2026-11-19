from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from ddtool.shell_shortcuts import MAX_MESSAGE, Activation


def send_activation(server_name: str, activation: Activation) -> bool:
    frame = activation.encode()
    if len(frame) > MAX_MESSAGE:
        return False
    deadline = time.monotonic() + 5
    client = QLocalSocket()
    while time.monotonic() < deadline:
        client.connectToServer(server_name)
        if client.waitForConnected(200):
            break
        client.abort()
        time.sleep(0.03)
    else:
        return False
    if client.write(frame) != len(frame):
        return False
    client.flush()
    return (client.bytesAvailable() > 0 or client.waitForReadyRead(3000)) and bytes(client.read(1)) == b"1"


def receive_activations(server: QLocalServer, activate: Callable[[Activation], None]) -> None:
    def read_client(client: QLocalSocket) -> None:
        client.setReadBufferSize(MAX_MESSAGE + 1)
        timer = QTimer(client, interval=3000, singleShot=True)
        timer.timeout.connect(lambda: client.abort())
        handled = False

        def read_frame() -> None:
            nonlocal handled
            if handled:
                return
            if client.bytesAvailable() > MAX_MESSAGE:
                client.abort()
                return
            if not client.canReadLine():
                return
            handled = True
            timer.stop()
            try:
                activation = Activation.decode(bytes(client.readLine()))
                if client.bytesAvailable():
                    raise ValueError("Unexpected activation data")
            except ValueError:
                client.abort()
                return
            client.write(b"1")
            client.disconnectFromServer()
            activate(activation)

        client.disconnected.connect(client.deleteLater)
        client.readyRead.connect(read_frame)
        timer.start()
        read_frame()

    def accept() -> None:
        while server.hasPendingConnections():
            read_client(server.nextPendingConnection())

    server.newConnection.connect(accept)
