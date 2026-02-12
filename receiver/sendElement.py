def sendMessageElement(accessToken, roomId, mensagem):
    msg = f'🤖 IntelliBot<br>🚨 ALERTA DE SISTEMA 🚨<br>{mensagem}'

    print_color(f"Enviando Msg {msg}\n", 33)

    url = f"https://cryptochat.com.br/_matrix/client/r0/rooms/{roomId}/send/m.room.message"

    post_data = {
        'msgtype': 'm.text',
        'body': msg,
        'format': 'org.matrix.custom.html',
        'formatted_body': msg,
    }

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {accessToken}',
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(post_data))
        response.raise_for_status()  # Raises a HTTPError for bad responses
        result = response.text
    except requests.exceptions.RequestException as e:
        print(f'Erro ao enviar a mensagem para o grupo: {e}', 31)

    return {
        'data': result,
        'status': response.status_code if response else 500
    }