import asyncio
import json
import os
from typing import Optional

from quart import Quart, jsonify, make_response, request
from quart.exceptions import Unauthorized

app = Quart(__name__)
clients = set()
datadict = {}


class ServerSentEvent:
    def __init__(
        self,
        data: str,
        *,
        event: Optional[str] = None,
        id: Optional[int] = None,
        retry: Optional[int] = None,
    ) -> None:
        self.data = data
        self.event = event
        self.id = id
        self.retry = retry

    def encode(self) -> bytes:
        message = f'data: {self.data}'
        if self.event is not None:
            message = f'{message}\nevent: {self.event}'
        if self.id is not None:
            message = f'{message}\nid: {self.id}'
        if self.retry is not None:
            message = f'{message}\nretry: {self.retry}'
        message = f'{message}\r\n\r\n'
        return message.encode('utf-8')


@app.before_request
async def check_auth():
    if request.endpoint == 'index':
        return
    auth = request.authorization
    if (
        auth is None
        or not auth.username
        or not auth.password
        or auth.username != os.environ.get('NOTHUB_USERNAME')
        or auth.password != os.environ.get('NOTHUB_PASSWORD')
    ):
        return await make_response(
            'Authorization required', 401, {'WWW-Authenticate': 'Basic realm="get out"'}
        )


@app.route('/')
async def index():
    response = await make_response('nothing to see here :)')
    response.content_type = 'text/plain'
    return response


@app.route('/data/')
async def get_data():
    return jsonify(datadict)


@app.route('/data/', methods=('DELETE',))
async def delete_data():
    datadict.clear()
    await _notify()
    return '', 204


@app.route('/data/', methods=('PATCH',))
async def patch_data():
    datadict.update(await request.get_json())
    await _notify()
    return jsonify(datadict)


@app.route('/data/', methods=('PUT',))
async def replace_data():
    datadict.clear()
    datadict.update(await request.get_json())
    await _notify()
    return jsonify(datadict), 201


@app.route('/data/<key>')
async def get_data_item(key):
    try:
        value = datadict[key]
    except KeyError:
        return '', 404
    return jsonify(value), 201


@app.route('/data/<key>', methods=('PUT',))
async def update_data_item(key):
    datadict[key] = value = await request.get_json()
    await _notify()
    return jsonify(value), 201


@app.route('/data/<key>', methods=('DELETE',))
async def delete_data_item(key):
    datadict.pop(key, None)
    await _notify()
    return '', 204


async def _notify():
    payload = json.dumps(datadict)
    for queue in clients:
        await queue.put(payload)


@app.route('/updates')
async def sse_updates():
    queue = asyncio.Queue()
    clients.add(queue)

    async def send_events():
        try:
            yield ServerSentEvent(json.dumps(datadict)).encode()
            while True:
                data = await queue.get()
                event = ServerSentEvent(data)
                yield event.encode()
        except asyncio.CancelledError:
            clients.remove(queue)
            raise

    response = await make_response(
        send_events(),
        {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Transfer-Encoding': 'chunked',
        },
    )
    response.timeout = None
    return response
