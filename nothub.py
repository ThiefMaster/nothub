import asyncio
import json
import os

from quart import Quart, jsonify, make_response, request

app = Quart(__name__)
clients = set()
datadict = {}


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
    data = await request.get_json()
    if data:
        datadict.update(data)
    await _notify()
    return jsonify(datadict)


@app.route('/data/', methods=('PUT',))
async def replace_data():
    data = await request.get_json()
    datadict.clear()
    if data:
        datadict.update(data)
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


def _sse(data):
    return f'data: {data}\r\n\r\n'.encode()


@app.route('/updates')
async def sse_updates():
    queue = asyncio.Queue()
    clients.add(queue)

    async def send_events():
        try:
            yield _sse(json.dumps(datadict))
            while True:
                data = await queue.get()
                yield _sse(data)
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
