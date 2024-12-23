import datetime
import streamlit as st
import pandas as pd
import requests
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from functools import wraps


current_month = datetime.datetime.now().month
if current_month in [12, 1, 2]:
    CURRENT_SEASON = 'winter'
elif current_month in [3, 4, 5]:
    CURRENT_SEASON = 'spring'
elif current_month in [6, 7, 8]:
    CURRENT_SEASON = 'summer'
else:
    CURRENT_SEASON = 'autumn'


def get_std_and_mean(frame):
    grouped_frame = frame.groupby(['city', 'season'])['temperature'].agg(['mean', 'std'])
    return grouped_frame


def use_pandas(frame):
    frame['mean'] = frame.groupby(['season', 'city'])['temperature'].transform('mean')
    frame['std'] = frame.groupby(['season', 'city'])['temperature'].transform('std')

    frame['аномальные данные'] = np.where(
        ((frame['mean'] + frame['std'] * 2) < frame['temperature']) | (
                (frame['mean'] - frame['std'] * 2) > frame['temperature']),
        True,
        False
    )
    return frame


def handle_exception():
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                response = func(*args, **kwargs)
                return response
            except requests.HTTPError as e:
                if e.response.status_code == 401:
                    return {
                        "cod": 401,
                        "message": "Invalid API key. Please see https://openweathermap.org/faq#error401 for more info."
                    }
                else:
                    return e
            except Exception as e:
                return e

        return wrapper

    return decorator


def get_latitude_and_longitude(city_name, api_key):
    url = r'http://api.openweathermap.org/geo/1.0/direct'
    params = {
        'q': city_name,
        'appid': api_key
    }
    resp = requests.get(url=url, params=params)
    if resp.ok:
        json_resp = resp.json()
        geographic_coordinates = {'lat': json_resp[0]['lat'], 'lon': json_resp[0]['lon']}
        return geographic_coordinates
    else:
        resp.raise_for_status()


def get_weather_data(geographic_coordinates: dict, api_key) -> float:
    url = r'https://api.openweathermap.org/data/2.5/weather'
    params = {
        'lat': geographic_coordinates['lat'],
        'lon': geographic_coordinates['lon'],
        'appid': api_key,
        'lang': 'ru',
        'units': 'metric'
    }
    resp = requests.get(url=url, params=params)
    if resp.ok:
        json_resp = resp.json()
        return json_resp['main']['temp']
    else:
        resp.raise_for_status()


@handle_exception()
def process_task(city, api_key):
    geographic_coordinates = get_latitude_and_longitude(city, api_key)
    weather_data = get_weather_data(geographic_coordinates, api_key)
    return weather_data


def visualize_weather(filtered_data):
    fig = px.line(
        filtered_data,
        x='timestamp',
        y='temperature',
        color='city',
        title='Температура по городам с выделением аномальных данных',
        labels={'timestamp': 'Дата', 'temperature': 'Температура (°C)', 'city': 'Город'},
        hover_data=['season']
    )

    anomalies = filtered_data[filtered_data['аномальные данные']]

    anomaly_cities = anomalies['city'].unique()

    color_map = px.colors.qualitative.Plotly
    unique_cities = filtered_data['city'].unique()
    city_colors = {city: color_map[i % len(color_map)] for i, city in enumerate(unique_cities)}

    for city in anomaly_cities:
        city_anomalies = anomalies[anomalies['city'] == city]
        fig.add_trace(
            go.Scatter(
                x=city_anomalies['timestamp'],
                y=city_anomalies['temperature'],
                mode='markers',
                marker=dict(
                    color=city_colors[city],
                    size=10,
                    symbol='circle',
                    line=dict(width=2, color='DarkSlateGrey')
                ),
                name=f'Аномальные данные - {city}',
                hovertemplate=(
                        'Город: %{text}<br>' +
                        'Дата: %{x}<br>' +
                        'Температура: %{y}°C<br>' +
                        'Сезон: %{customdata[0]}<br>' +
                        '<extra></extra>'
                ),
                text=city_anomalies['city'],
                customdata=city_anomalies[['season']]
            )
        )

    fig.update_layout(
        legend_title_text='Город',
        legend=dict(
            itemsizing='constant'
        )
    )
    return fig


st.title("Анализ данных погоды")

st.header("Загрузите датасет")

uploaded_file = st.file_uploader("Выберите CSV-файл", type=["csv"])
data = None
if uploaded_file:
    data = pd.read_csv(uploaded_file)
    flag = True
    st.write("Превью данных:")
    st.dataframe(data)
    city_selection = st.multiselect("Выберите город для отображения", options=data.city.unique())
    if city_selection:
        filtered_data = data[data['city'].isin(city_selection)]
        if st.button("Отобразить дополнительную информацию"):
            st.write("Описательная статистика:")
            grouped_filtered_data = filtered_data.groupby(['city', 'season'])['temperature']
            st.dataframe(grouped_filtered_data.describe())

            filtered_data = use_pandas(filtered_data).reset_index(drop=True)
            filtered_data['timestamp'] = pd.to_datetime(filtered_data['timestamp'])
            st.write("Сезонные профили:")
            std_and_mean = get_std_and_mean(filtered_data)
            st.dataframe(std_and_mean)

            fig = visualize_weather(filtered_data)
            st.plotly_chart(fig)

st.header("Загрузите данные API")
with st.form("weather_form"):
    api_key = st.text_input("Введите ваш OpenWeatherMap API-ключ")
    city = st.text_input("Введите город")
    submit_btn = st.form_submit_button("Показать погоду")
    if city and api_key:
        weather = process_task(city, api_key)
        if issubclass(type(weather), BaseException):
            st.write(weather)
        elif isinstance(weather, dict):
            st.write(weather)
        elif (data is not None) and (not data.empty) and (weather is not None) and (isinstance(weather, (int, float))):
            filtered_data = data[data['city'].isin([city]) & (data['season'] == CURRENT_SEASON)]
            std = filtered_data['temperature'].std()
            mean = filtered_data['temperature'].mean()

            if (weather > (mean + 2 * std)) or (weather < (mean - 2 * std)):
                temperature_message = 'Погода отличается от нормальной'
            else:
                temperature_message = 'Погода нормальная'
            st.write(f"Сейчас погода в городе {city}: {weather}. {temperature_message}")
        else:
            st.write(f"Сейчас погода в городе {city}: {weather}.\nЗагрузите исторические данные "
                     f"чтобы узнать является ли актуальная температура нормальной.")
