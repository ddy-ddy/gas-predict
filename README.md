## gas-predict

- 预测智能合约的gas消耗



## 数据收集，分析与处理

- 利用爬虫技术从数据平台 EtherScan 爬取约4万个部署的 Solidity 智能合约源代码和90万条Gas消耗样本
- 分析数据的特征，根据制定的两个智能合约相似的标准对数据进行去重
- 统计数据的频率，对重的数据进行过采样处理来解决数据存在长尾分布的问题



## 主要功能

- 1、上传自己的智能合约
- 2、点击提交后，后端服务器将会预测智能合约的gas消耗
- 3、网页将会展示智能合约的代码以及可视化各个函数的预测结果



## 运行流程

#### 1. backend

- 环境要求：`python3.7`

```shell
cd backend
pip install - r requirements.txt
python app.py
```

#### 2. frontend

- 环境要求：`node版本：16.14.0`, `npm版本：8.3.1`

```shell
cd frontend
npm install
npm run dev
```



## 运行结果

- web初始页面
  ![](https://tva1.sinaimg.cn/large/e6c9d24egy1h31nqmrxw1j21c00u075f.jpg)

- 上传自己的智能合约后的页面
    - 左边是智能合约的代码
    - 右边是各个函数对于的预测结果可视化
    ![](https://tva1.sinaimg.cn/large/e6c9d24egy1h31nssyzjej21c00u0gp5.jpg)