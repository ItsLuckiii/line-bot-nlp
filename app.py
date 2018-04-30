# -*- coding: utf-8 -*-

#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.

import os
import sys
from argparse import ArgumentParser
from pythainlp import word_tokenize
from keras.models import model_from_json
import pickle
import pymysql
import datetime
import json
import numpy as np
import pandas as pd

# Connect to the database
connection = pymysql.connect(host='sql12.freemysqlhosting.net',
                             user='sql12235366',                                                   
                             password='49VyS4LHJS',
                             database='sql12235366')

from flask import Flask, request, abort
from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
)
# kuy
app = Flask(__name__)

# get channel_secret and channel_access_token from your environment variable
channel_secret = 'c4b455f1d8e88c5de6983e43265adf0b'
channel_access_token = 'OMpCqFAGvSDFd9t6ASr8it5mcczoFaYP0kzN1aYlleVG+3phImUopXeqF68SeYXcpWLOn1XsRdkdAG5WCIuV3SUA08d7hd2KnVpYI5STDy2rexGzkvvAVJsAUjsu4gG+KvgUPaF73i5r6LRlyqlbCAdB04t89/1O/w1cDnyilFU='
if channel_secret is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if channel_access_token is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)

with open('intent_arch.json') as json_data:
    intent_arch = json_data.read()
intent =  model_from_json(intent_arch)
intent.load_weights('model_weights.h5')
dictionary = pickle.load(open('dictionary.pickle','rb'))
brand_dict_map = {'iphone':'apple','ไอโฟน':'apple','galaxy':'samsung'}

mobile_df = pd.read_csv('mobile.csv',names=['brand','model','price','color','capacity','description'])
mobile_df.color = mobile_df.color.apply(lambda k: ':'.join([clean_color(s) for s in k.split(':')]))
mobile_df.model = mobile_df.model.apply(lambda k: clean_model(k))
mobile_df.head()
mobile_df.describe(include='all')

data_df = pd.read_csv('data.csv',names=[0])
data_df = data_df.drop_duplicates().dropna()
sentence = data_df.applymap(lambda k: clean_sentence_for_tagging(k))
data_df = data_df.assign(sentence=sentence)
data_df = data_df[data_df['sentence']!=""]
data_df = data_df.drop([0], axis=1)

color_dict = np.load('./color_dict.npy')
color_dict = np.vectorize(lambda k: ':'.join([clean_color(s) for s in k.split(':')]))(color_dict)
color_dict = np.unique(color_dict)

brand_dict = np.load('./brand_dict.npy')

model_dict = np.load('./model_dict.npy')
model_dict = np.vectorize(clean_model)(model_dict)
model_dict = np.unique(model_dict)

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

def to_index(sen):
    ret = []
    for word in sen:
        try:
            ret.append(dictionary[word])
        except KeyError:
            ret.append(dictionary['UNK'])
    return ret

def get_intention(sentence):
    data = word_tokenize(sentence)
    data = to_index(data)
    data = data[:49] + [0]*(49 - len(data))
    data = np.array([data])
    intention = intent.predict(data)
    # print(intention)
    intention = intention[0].argmax()
    # print(intention)
    return intention

def predict_tag(sen, debug=True):
    current_brand = ''
    current_model = ''
    current_color = ''
    current_capacity = ''
    current_desc = ''
    if debug:
        print('sen:',sen)
    for brand in brand_dict:
        if sen.find(brand) != -1:
            if debug:
                print('brand = ',brand)
            current_brand = brand
            break
    if current_brand == '':
        for brand,mapped_brand in brand_dict_map.items():
            if sen.find(brand) != -1:
                if debug:
                    print('brand = ',mapped_brand)
                current_brand = mapped_brand
                break
    if current_brand == '':
        if debug:
            print('no brand')
#         break
    for model in model_dict:
        if sen.lower().find(model) != -1:
            if debug:
                print('model = ',model)
            current_model = model
            break
    if current_model == '':
        if debug:
            print('no model')
#         break
    for color in color_dict:
        if sen.lower().find(color) != -1:
            if debug:
                print('color = ',color)
            current_color = color
            break
    if current_color == '':
        if debug:
            print('no color')
#         break
    for capa in [8,16,32,64,128,256,512]:
        if re.search(r'{}\s*[Gg][Bb]'.format(capa),sen):
            current_capacity = capa
    if current_brand !='' and current_model != '':
        # not sure should use head or not??
        current_desc = mobile_df[(mobile_df['brand'] == current_brand) & (mobile_df['model']==current_model)].head(1)
        if debug:
            print('desciption:\n',current_desc['description'])
    
    return current_brand, current_model, current_color, current_capacity, current_desc

"""
DB (session_id,brand,model,capa,color,price)
"""
def escape_name(s):
    """Escape name to avoid SQL injection and keyword clashes.

    Doubles embedded backticks, surrounds the whole in backticks.

    Note: not security hardened, caveat emptor.

    """
    return '`{}`'.format(s.replace('`', '``'))

def get_user(userid,items):
    cursor = connection.cursor()
    query = "SELECT * FROM chatbot WHERE `session_id`=%s"
    cursor.execute(sql, (userid))
    result = cursor.fetchone()
    # names = list(items)
    # cols = ', '.join(map(escape_name, names))
    if not result:
        sql = "INSERT INTO `chatbot` (`session_id`) VALUES (%s)"
        cursor.execute(sql, (userid))
        connection.commit()
    #     query = "INSERT IGNORE INTO chatbot (session_id, ,brand,model,capa,color,price) VALUES (%s, %s,%s, %s,%s)"
    #     cursor.execute(query, items)
    # else:
    #     ss = zip(cols, list(items.values())
    #     query = 'UPDATE chatbot SET session_id =%s,brand = %s,model = %s,capa=%s,color=%s,price=%s WHERE `session_id`=%s'.format(ss[0],ss[1],userid)
    #     cursor.execute(query, items)
    # query = "INSERT IGNORE INTO chatbot (session_id, ,brand,model,capa,color,price) VALUES (%s, %s,%s, %s,%s)"
    # cursor.execute(query, items)
    return result



intent_dict ={0:'<PRICE>',1:'<INFO>',2:'<BUY>'}

def get_ans(message,intent,userid):
    # tokens = word_tokenize(message)
    print("getting ans")
    prediction = intent_dict[intent]
    print("got intent",prediction)

    current_brand,current_model,current_color,current_capacity,current_desc = predict_tag(message,debug=True)
    
    print("getting tag")
    answer = ''
    if current_brand == '':
        answer = 'กรุณาระบุยี่ห้อด้วยครับ'
    elif current_model == '':
        answer = 'กรุณาระบุรุ่นด้วยครับ'
    elif prediction == '<PRICE>':
        if current_brand == 'apple':
            if current_capacity == '':
                answer = 'กรุณาระบุขนาดความจุด้วยครับ'
            else:
                answer = mobile_df[(mobile_df.brand=='apple')&
                                   (mobile_df.model==current_model)&
                                   (mobile_df.capacity==current_capacity)]['price']
        else:
            answer = mobile_df[(mobile_df.brand==current_brand)&
                               (mobile_df.model==current_model)]['price']
    elif prediction == '<INFO>':
        if current_brand == 'apple':
            if current_capacity == '':
                answer = 'กรุณาระบุขนาดความจุด้วยครับ'
            else:
                answer = mobile_df[(mobile_df.brand=='apple')&
                                   (mobile_df.model==current_model)&
                                   (mobile_df.capacity==current_capacity)]['description']
        else:
            answer = mobile_df[(mobile_df.brand==current_brand)&
                               (mobile_df.model==current_model)]['description']
    elif prediction == '<BUY>':
        if current_color == '':
            answer = 'กรุณาระบุสีที่ต้องการด้วยครับ'
        elif current_brand == 'apple':
            if current_capacity == '':
                answer = 'กรุณาระบุขนาดความจุด้วยครับ'
            elif current_address == '':
                answer = 'กรุณาระบุที่อยู่สำหรับรับสินค้าด้วยครับ'
            else:
                answer = """กรุณายืนยันการสั่งสินค้าด้วยครับ
                            brand: {}
                            model: {}
                            color: {}
                            capacity: {}
                            address: {}""".format(current_brand,
                                                  current_model,
                                                  current_color,
                                                  current_capacity,
                                                  current_address)
        elif current_address == '':
            answer = 'กรุณาระบุที่อยู่สำหรับรับสินค้าด้วยครับ'
        else:
            answer = """กรุณายืนยันการสั่งสินค้าด้วยครับ
                        brand: {}
                        model: {}
                        color: {}
                        address: {}""".format(current_brand,
                                              current_model,
                                              current_color,
                                              current_address)
    return answer

@handler.add(MessageEvent, message=TextMessage)
def message_text(event):
    message = event.message.text
    userid = event.source.user_id
    # print(message)
    intention = get_intention(message)
    ans=get_ans(message,intention,userid)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=(ans))
    )


if __name__ == "__main__":
    arg_parser = ArgumentParser(
        usage='Usage: python ' + __file__ + ' [--port <port>] [--help]'
    )
    arg_parser.add_argument('-p', '--port', default=8000, help='port')
    arg_parser.add_argument('-d', '--debug', default=False, help='debug')
    options = arg_parser.parse_args()

    app.run(debug=options.debug, port=options.port)
