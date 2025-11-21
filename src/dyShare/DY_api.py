import requests




url = "http://192.168.2.27:8080/siberianNitraria/verifyActivate"
data = {
    "siberian": "7CYY4TIx8n5tjpmWaxexJLjaPaM/0Y9lR2fs34HfNqk=",
    "deviceCode": "设备1"
}

response = requests.post(url, json=data)
print(response.json())
if response.status_code == 200:
    result = response.json()
    print("响应结果:", result)
    if result.get('code') == 200:
        print("✅ 激活验证成功！")
    else:
        print("❌ 卡密不存在！")
