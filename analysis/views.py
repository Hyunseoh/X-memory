import datetime
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.test import tag
from django.utils import timezone
from requests import request
from album.forms import UserForm, PhotoForm
from album.models import Photo, PhotoTag, AnalysisResult
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import logging
import boto3
from botocore.exceptions import ClientError
from django.views.decorators.csrf import csrf_exempt
import os
import time
import mimetypes
# import models
# import requests
# import jsonresponse

import io
from PIL import Image
#import cv2
import numpy as np
from base64 import b64decode
# from .utils import *
# from .Darknet import DarkNet

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.http import JsonResponse
from django.views.generic import View

import pandas as pd
import pymysql
import collections
import googlemaps
from PIL import Image
import matplotlib.pyplot as plt
from folium import plugins
import folium
from matplotlib import font_manager, rc
import seaborn as sns


#위치 가져오기 위해 api접근
gmaps = googlemaps.Client(key='AIzaSyDlTe2iwy53wvvt8WNwJ15fgzLGNmAQpf8')


# 장소 분석 페이지 관련 함수

# 사진 많이 찍은 위치를 지도에 표시하는 함수
def myplace(tag_table):
    # 인풋값으로 태그테이블에 photo_id로 참조된 location필드가 merge된 데이터프레임을 받아옴
    if 'location' in tag_table.columns:  # 사진의 위치값이 없으면 코드 실행X
        place_list = tag_table['location'].str.split()
        tag_table['city'] = place_list.str.get(1)
        tag_table['locality'] = place_list.str.get(2)
        placeTaken_photo = tag_table.drop_duplicates(['photo_id'])['locality'].value_counts()[0:3]
        placeTaken_photo = pd.DataFrame(placeTaken_photo)
        # 같은 날 찍은 사진도 카운팅됨
        # 자주 방문 분석을 위해서 create_Date 추가 코드 필요
        placeTaken_photo['index'] = placeTaken_photo.index
        placeTaken_photo
        places = list(placeTaken_photo.index)
        i = 0
        lat = []  # 위도
        lng = []  # 경도
        for place in places:
            i = i + 1
            try:
                geo_location = gmaps.geocode(place)[0].get('geometry')
                lat.append(geo_location['location']['lat'])
                lng.append(geo_location['location']['lng'])

            except:
                pass
        # 데이터프레임만들어 출력하기
        df = pd.DataFrame({'위도': lat, '경도': lng}, index=places)
        placeTaken_photo = pd.concat([df, placeTaken_photo], axis=1)
        placeTaken_photo = placeTaken_photo.rename(columns={'locality': 'num'})
        placeTaken_photo
        coords = placeTaken_photo[['위도', '경도']]
        coords = list(zip(coords['위도'], coords['경도']))

        m = folium.Map(
            location=(35.95, 128.25),
            zoom_start=7
        )
        for i in range(3):
            fav_place_photo = tag_table[tag_table['locality'] == places[i]]['photo_id'].value_counts().index[0]
            # 나중에 가져올 values를 thumnail로 바꾸는 것 고려
            fav_place_photo_img = str(
                list(Photo.objects.filter(id=fav_place_photo).values_list('thumbnail', flat=True))[0])

            myPhoto = '<img src= ' + fav_place_photo_img + '>'
            # 이미지 링크를 가져와 띄우면 사진 크기가 안맞음
            ##### 링크가 아닌 이미지로 가져와서 리사이징을 하면 크기 맞게 띄울 수는 있는데
            # 이미지가 계속 쌓여서 굳이 저장하고싶진 않다 하지만 일단 구현은 해놓는게 좋겠지,,

            # myphoto = 'X-travel-djanjo/analysis/지도에뜸.png'
            # urllib.request.urlretrieve(fav_place_photo_img, myphoto)
            # myPhoto = Image.open('X-travel-djanjo/analysis/지도에뜸.png')
            # myPhoto = myPhoto.resize((256, 256))

            iframe = folium.IFrame(myPhoto, width=300, height=300)
            popup = folium.Popup(iframe, max_width=750)

            folium.Marker(coords[i],
                          popup=popup,
                          tootip=str(placeTaken_photo['num'][i]) + '개의 사진을 찍었어요!').add_to(m)
        maps = m._repr_html_()
    else:
        m = folium.Map(
            location=(35.95, 128.25),
            zoom_start=7
        )
        maps = m._repr_html_()

    return maps


def analysisPlace(request):
    user = get_user_model()
    photo_id_list = list(Photo.objects.filter(author_id=request.user.id).values_list('id', flat=True))
    photo_id = ','.join(map(str, photo_id_list))

    tag_table = get_table(user, photo_id, 'phototag')  # 여기에 place열 있어야함
    analysisresult_tb = get_table(user, photo_id, 'analysisresult')
    if analysisresult_tb.empty == False:
        tag_table = pd.merge(tag_table, analysisresult_tb, how='left', left_on='photo_id', right_on='photo_id')

    maps = myplace(tag_table)
    return render(request, 'analysisPlace.html', {'map': maps})


# 시간대 분석 함수 시작 ########################################
def time_tag(tag_table):
    df = tag_table.copy()
    df['timezone'] = '점심'
    df['create_date'] = pd.to_datetime(df['create_date'])

    dawn = df.loc[df['create_date'].dt.hour < 5].index
    df.loc[dawn, 'timezone'] = '새벽'

    morning = df.loc[(df['create_date'].dt.hour >= 5) & (df['create_date'].dt.hour < 9)].index
    df.loc[morning, 'timezone'] = '아침'

    evening = df.loc[(df['create_date'].dt.hour >= 17) & (df['create_date'].dt.hour < 21)].index
    df.loc[evening, 'timezone'] = '저녁'

    night = df.loc[(df['create_date'].dt.hour >= 21) & (df['create_date'].dt.hour < 24)].index
    df.loc[night, 'timezone'] = '밤'
    # df.groupby('tags').count()
    # table = df.groupby('timezone').count()

    # 시간별(0~23시) 가장 인기 태그 top1 분석 그래프
    df['hour'] = df['create_date'].dt.hour
    hourtags = df[['hour', 'tags']]

    hour_maxtag = []
    for i in range(24):
        hour_maxtag.append(collections.Counter(hourtags[hourtags['hour'] == i]['tags']).most_common(1))

    for i in range(24):
        if len(hour_maxtag[i]) == 0:  # 빈 리스트일 경우
            hour_maxtag[i] = [('', 0)]

    # tag,freq 리스트 형태로 만들기
    tag = []
    freq = []
    hour = list(range(24))
    for j in range(24):
        tag.append(hour_maxtag[j][0][0])
        freq.append(hour_maxtag[j][0][1])

    plt.rc('font', family='nanumgothic')
    plt.figure(figsize=(8, 5))
    plt.title("시간별 인기 태그", size=20, loc='left', pad=15)
    plt.plot(hour, freq, color='green', marker='o',linestyle='--', markersize=9)
    plt.xticks(np.arange(0, 24))
    plt.yticks(np.arange(min(freq), max(freq) + 2))
    plt.xlabel('시', size=15)
    plt.ylabel('빈도', size=15)
    for index, value in enumerate(freq):
        plt.text(index - 0.5, value + 0.3, str(tag[index]), fontsize=15)  # 수치텍스트
    plt.savefig('C:\PythonStudy\X-travel-django\X-travel-django\static\images\graphtime(24).png')
    plt.clf()

    return df # timezone_tag에 쓰기 위한 반환값

import numpy as np
def timezone_tag(df):
    # 시간대별 ('아침', '점심', '저녁', '밤', '새벽') 태그 5순위까지 분석
    for time in ['아침', '점심', '저녁', '밤', '새벽']:
        timezone_tb = df[df['timezone'] == time]

        table_timegroup = timezone_tb.drop(timezone_tb.columns[[2, 3, 4, 5, 6, 7, 8, 9]], axis=1).groupby(
            'tags').count().sort_values(by=['id'], ascending=False).head(5)

        if (len(table_timegroup.index) < 5):
            pass
        else:
            label = list(table_timegroup.index)
            index = list(table_timegroup['id'])

            x = label
            y = index

            plt.figure(figsize=(9, 7))
            plt.rc('font', family='nanumgothic')
            plt.barh(x, y, color=sns.color_palette('Set2'))

            plt.title(str(time) + ' 시간대 인기 태그', size=20, loc='left', pad=15)
            plt.yticks(size=14)

            if (y[0] == y[1]) and (y[1] == y[2]) and (y[2] == y[3]) and (y[3] == y[4]):
                plt.xlabel('빈도', fontsize=15)
                plt.xticks(np.arange(y[0], y[0]+3))

            else:
                plt.xlabel('빈도', fontsize=15)
                plt.xticks(np.arange(0,max(y)+3))

            for index, value in enumerate(y):
                plt.text(value+0.15, index - 0.1, str(value), fontsize=15)  # 수치텍스트
            plt.savefig('C:\PythonStudy\X-travel-django\X-travel-django\static\images\graphtime_'+time+'.png')
            plt.clf()

    # 1시간 단위 태그 top1 분석
    # df['hour'] = df['create_date'].dt.hour
    # hourtags = df[['hour', 'tags']]
    #
    # collections.Counter(hourtags['tags']).most_common(5)






# 요일별 분석 함수 (수정 후) ##################################
import collections
from matplotlib import font_manager, rc

def weekday_tag(tag_table): # 일~토 인기 태그 top1개씩 한 그래프에
    df = tag_table.copy()

    # 요일별 5순위까지 그래프 생성
    font_path = "C:/Windows/Fonts/NGULIM.TTF"
    font = font_manager.FontProperties(fname=font_path).get_name()
    rc('font', family=font)

    df['create_date'] = pd.to_datetime(df['create_date'])
    df['weekday'] = df['create_date'].dt.weekday  # 요일 추출

    weekdaytag_df = df[['tags', 'weekday']]  # 필요한 열로만 df 다시 만듦

    # 일~토 top1 태그 추출해 그래프 생성
    commontags_lst = []
    for i in range(7):
        commontags_lst.append(collections.Counter(weekdaytag_df[weekdaytag_df['weekday'] == i]['tags']).most_common(5))

    mostcommon_byweekday = []
    for j in range(7):
        mostcommon_byweekday.append(commontags_lst[j][0])
    mostcommon_byweekday = pd.DataFrame(mostcommon_byweekday)

    plt.rc('font', family='nanumgothic')
    plt.figure(figsize=(7, 5))
    plt.bar(mostcommon_byweekday.index, mostcommon_byweekday[1], color=sns.color_palette('Set2'))
    plt.xticks([0, 1, 2, 3, 4, 5, 6], labels=['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'])
    plt.yticks(np.arange(0, max(mostcommon_byweekday[1]) + 3))
    plt.xlabel('요일', size=13)
    plt.ylabel('빈도', size=13)
    for index, value in enumerate(mostcommon_byweekday[1]):
        plt.text(index - 0.25, value + 0.3, str(mostcommon_byweekday[0][index]), size=12)
    plt.title("요일별 인기 태그", size=20, loc='left', pad=15)
    plt.savefig('C:\PythonStudy\X-travel-django\X-travel-django\static\images\graphweekday.png') # 저장

    plt.clf()  # Clear the current figure

    weekday = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일']
    for row in range(7):
        tags_byweekend = pd.DataFrame(commontags_lst[row])

        tags = list(tags_byweekend[0][0:4])  # top4 태그명
        freq = list(tags_byweekend[1][0:4])  # top4 빈도 수

        other_freq = sum(tags_byweekend[1][4:])  # 나머지는 기타로 처리
        tags.append('기타')
        freq.append(other_freq)

        wedgeprops = {'width': 0.7, 'edgecolor': 'w', 'linewidth': 5}

        plt.rc('font', family='nanumgothic')
        plt.figure(figsize=(7, 7))
        plt.pie(freq, labels=tags, autopct='%.1f%%', textprops={'fontsize': 14}, colors=sns.color_palette("Set3"),
                wedgeprops=wedgeprops)
        plt.title(str(weekday[row]) + '의 인기 태그', size=20, loc='left', pad=15)
        plt.savefig('C:\PythonStudy\X-travel-django\X-travel-django\static\images\graph_'+str(weekday[row]) +'.png')  # 저장
        plt.clf()
        #이미지 저장 경로 수정 필요(db에 user.id와 같이 업로드)



# 디테일 페이지1 #############################################
def analysisTime(request):
#DB에서 정보를 받아옴
#받아온 정보를 변수에 저장

# 변수 = 함수(DB정보)
# 함수(위의 변수)
#
    user = get_user_model()
    photo_id_list=list(Photo.objects.filter(author_id=request.user.id).values_list('id', flat=True))
    photo_id=','.join(map(str, photo_id_list))
    # MySQL Connection 연결하고 테이블에서 데이터 가져옴
    conn = pymysql.connect(host='18.219.244.45', user='python', password='python',db='mysql_db', charset='utf8')
    curs = conn.cursor(pymysql.cursors.DictCursor)
    sql = 'select * from album_phototag where photo_id in (' + photo_id +')'
    curs.execute(sql)
    rows = curs.fetchall()
    tag_table = pd.DataFrame(rows)



    weektag = weekday_tag(tag_table)


    timetag = time_tag(tag_table)
    timezonetag = timezone_tag(timetag)


    content={
        'timezonetag':timezonetag,
        'weektag':weektag
    }

    return render(request,'analysisTime.html', content)



#수정
