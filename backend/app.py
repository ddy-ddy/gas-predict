# -*- coding: utf-8 -*-
# @Time    : 2022/6/7 10:01 下午
# @Author  : ddy
# @FileName: app.py.py
# @github  : https://github.com/ddy-ddy

from flask import Flask, request, make_response
from flask_cors import CORS
import pandas as pd

app = Flask(__name__)
CORS(app)


# 获取example
@app.route("/example")
def get_example_sol():
    data = pd.read_csv("utils/data.csv")
    all_info = []
    for i, item in enumerate(data["name"]):
        all_info.append([item, eval(data["data"].iloc[i])])
    all_info = all_info[:4]
    with open("test_contracts/AirDrop.sol", 'r') as f:
        result = {"code": str(f.read()), "data": all_info}
    return make_response(result)


# 用户上传文件，返回相应的结果
@app.route("/upload", methods=["POST", "GET"])
def upload():
    if request.method == 'POST':
        data = pd.read_csv("utils/data.csv")
        all_info = []
        for i, item in enumerate(data["name"]):
            all_info.append([item, eval(data["data"].iloc[i])])
        with open("test_contracts/AirDrop.sol", 'r') as f:
            result = {"code": str(f.read()), "data": all_info}
        return make_response(result)


if __name__ == '__main__':
    app.run(debug=True)
