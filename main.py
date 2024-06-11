from flask import Flask, render_template, request, redirect, session, url_for, send_file, jsonify
import vk_api
import logging
from concurrent.futures import ThreadPoolExecutor
import json
import csv
from datetime import datetime

app = Flask(__name__)
def get_timestamp_from_date(date_str):
    date = datetime.strptime(date_str, '%Y-%m-%d')
    timestamp = int(date.timestamp())
    return timestamp
class DataStorage:
    formatted_data = []
    owner_id = 0
    @classmethod
    def clear_data(cls):
        cls.formatted_data.clear()

    @classmethod
    def append_data(cls, data):
        cls.formatted_data.append(data)

    @classmethod
    def get_data(cls):
        return cls.formatted_data

def get_timestamp_from_date(date_str):
    date = datetime.strptime(date_str, '%Y-%m-%d')
    timestamp = int(date.timestamp())
    return timestamp
class VKDataHandler:

    def __init__(self, token):
        self.vk_session = vk_api.VkApi(token=token)
        self.vk = self.vk_session.get_api()

    def get_user_info(self, user_id):
        try:
            user_info = self.vk.users.get(user_ids=user_id, fields="domain,counters,photo_max,sex,bdate,city,country")
            return user_info[0]
        except Exception as e:
            logging.error(f"Ошибка при получении информации о пользователе: {e}")
            return None

    def get_wall_posts(self, owner_id, count=None, start_date=None, end_date=None, min_likes=None, min_comments=None,
                       min_reposts=None, min_views=None, sort_by=None, sort_order='desc'):
        all_posts = []
        offset = 0
        count_within_date_range = 0

        while True:
            # Получение постов с заданными параметрами
            posts = self.vk.wall.get(owner_id=owner_id, count=100, offset=offset, extended=1)['items']

            # Если постов больше нет, выходим из цикла
            if not posts:
                break

            for post in posts:
                #print('------------------------------------------------------------------------------------------------------------------')
                #print(post)
                post_date = datetime.fromtimestamp(post['date'])
                post['formatted_date'] = post_date.strftime('%Y-%m-%d %H:%M:%S')  # Добавление отформатированной даты

                if start_date and post_date < start_date:
                    count_within_date_range = 1
                    continue
                if end_date and post_date > end_date:
                    continue
                # Применение фильтров по количественным параметрам
                if min_likes and post['likes']['count'] < min_likes:
                    continue
                if min_comments and post['comments']['count'] < min_comments:
                    continue
                if min_reposts and post['reposts']['count'] < min_reposts:
                    continue
                if min_views and post['views']['count'] < min_views:
                    continue

                all_posts.append(post)

            # Увеличение offset для получения следующей порции постов
            offset += 100

            if (start_date or end_date) and count_within_date_range == 1:
                break
            # Прекращение сбора постов, если уже набрано необходимое количество
            if count and len(all_posts) >= count:
                break

        # Ограничение числа постов до заданного параметра count, если count задан
        if count:
            all_posts = all_posts[:count]

        # Сортировка постов
        if sort_by:
            if sort_by == 'views_count':  # Сортировка по количеству просмотров
                reverse = True if sort_order == 'desc' else False
                all_posts = sorted(all_posts, key=lambda x: x['views']['count'], reverse=reverse)
            else:
                reverse = True if sort_order == 'desc' else False
                all_posts = sorted(all_posts, key=lambda x: x[sort_by]['count'], reverse=reverse)
        else:
            # Сортировка по дате по умолчанию
            reverse = True if sort_order == 'desc' else False
            all_posts = sorted(all_posts, key=lambda x: x['date'], reverse=reverse)

        return all_posts

    def get_user_groups(self, user_id):
        try:
            user_groups = self.vk.groups.get(user_id=user_id)
            total_groups = len(user_groups['items'])
            categories_count = {}

            for group_id in user_groups['items']:
                group_info = self.vk.groups.getById(group_id=group_id, fields='activity,type')
                if group_info and group_info[0]['type'] == 'group':
                    continue
                if not group_info or 'activity' not in group_info[0]:
                    continue
                category = group_info[0]['activity']
                print(category)
                categories_count[category] = categories_count.get(category, 0) + 1

            sorted_categories = sorted(categories_count.items(), key=lambda x: x[1], reverse=True)

            result = []

            for category, count in sorted_categories:
                percentage = (count / total_groups) * 100
                result.append((category, count, percentage))

            for category, count, percentage in result:
                print(f"Категория: {category}, Количество групп: {count}, Процент от общего числа: {percentage:.2f}%")

            return result

        except vk_api.VkApiError as error:
            print("Произошла ошибка при получении списка групп пользователя:", error)


    def get_group_info_by_id(self, group_id):
            try:
                group_info = self.vk.groups.getById(group_id=group_id, fields="city,description, members_count")
                return group_info[0]
            except Exception as e:
                logging.error(f"Ошибка при получении информации о группе: {e}")
                return None

    def get_groups(self, search_query, count=None, sort=None, market=None):
        try:
            DataStorage.clear_data()
            communities = self.vk.groups.search(q=search_query, count=count, sort=sort, market=market)['items']
            group_ids = [community['id'] for community in communities]

            with ThreadPoolExecutor() as executor:
                additional_infos = executor.map(self.get_group_info_by_id, group_ids)

            for community, additional_info in zip(communities, additional_infos):
                if additional_info:
                    community_data = {
                        'name': community['name'],
                        'id': community['id'],
                        'screen_name': community['screen_name'],
                        'is_closed': community['is_closed'],
                        'type': community['type'],
                        'photo_200': community['photo_200'],
                        'members_count': additional_info.get('members_count'),
                        'description': additional_info.get('description'),
                    }
                    DataStorage.append_data(community_data)

            return DataStorage.formatted_data
        except Exception as e:
            logging.error(f"Ошибка при получении информации о группах: {e}")
            return None

class DataExporter:
    @staticmethod
    def save_to_json(data, file_path):
        try:
            with open(file_path, 'w', encoding='utf-8') as json_file:
                json.dump(data, json_file, ensure_ascii=False, indent=4)
            print("Данные сохранены в JSON файл успешно.")
        except Exception as e:
            print(f"Ошибка при сохранении данных в JSON файл: {e}")

    @staticmethod
    def save_posts_to_json(data, file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    @staticmethod
    def save_to_csv(data, file_path):
        fieldnames = ['name', 'id', 'screen_name', 'is_closed', 'type', 'photo_200', 'members_count', 'description']
        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for group in data:
                if all(key in group for key in fieldnames):
                    writer.writerow(group)
                else:
                    print(f"Пропущена запись группы {group['name']}, так как не хватает ключей")
    @staticmethod
    def save_posts_to_csv(posts, filename):
        fieldnames = ['id', 'text', 'date', 'likes_count', 'comments_count', 'reposts_count', 'views_count', 'url_photos']

        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for inner_list in posts:
                for post in inner_list:
                    writer.writerow(post)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'user_id' in request.form:
            user_id = request.form.get("user_id")
            user_info = vk_data_handler.get_user_info(user_id)
            if user_info:
                return render_template("result.html", user_info=user_info)
            else:
                error_msg = "Ошибка при получении информации о пользователе. Пожалуйста, проверьте ID пользователя."
                logging.error(error_msg)
                return error_msg
        elif 'group_id' in request.form:
            group_id = request.form.get("group_id")
            group_data = vk_data_handler.get_groups(group_id)
            if group_data:
                return render_template("groups_search.html", group_info=group_data)
            else:
                error_msg = "Ошибка при получении информации о группе. Пожалуйста, проверьте ID группы."
                logging.error(error_msg)
                return error_msg
    return render_template("index.html")

@app.route('/groups_search', methods=['POST'])
def groups_search():
    if request.method == 'POST':
        search_query = request.form.get("search_query")
        count = request.form.get("count")
        if count == "":
            count = 10  # Устанавливаем значение по умолчанию в 5

        switch_value = request.form.get('sort_by_subscribers')
        with_market = request.form.get('with_market')
        market = 0
        print(switch_value)
        if switch_value == 'on':
            sort = 6
        else: sort = 0

        if with_market == 'on':
            market = 1
        else: sort = 0
        print("Search Query:", search_query)  # Добавим эту строку для отладки
        print("Count:", count)  # Добавим эту строку для отладки
        print("Sort:", sort)  # Добавим эту строку для отладки
        group_data = vk_data_handler.get_groups(search_query=search_query, count=count, sort=sort, market=market)  # Передаем search_query в функцию get_groups
        if group_data:
            return render_template("groups_search.html", group_info=group_data)
        else:
            error_msg = "Ошибка при получении информации о группах. Пожалуйста, попробуйте снова."
            logging.error(error_msg)
            return error_msg
    return "Метод не разрешен"

@app.route('/group/<int:group_id>/posts', methods=['GET','POST'])
def group_posts(group_id):
    if request.method == 'POST':
        print('Начало обработки POST запроса')
        print(group_id)
        print('Форма данных:', request.form)
        count = int(request.form['count']) if request.form['count'] else None
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d') if request.form['start_date'] else None
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d') if request.form['end_date'] else None
        start_date_str = start_date.strftime('%Y-%m-%d') if request.form['start_date'] else None
        end_date_str = end_date.strftime('%Y-%m-%d') if request.form['end_date'] else None
        min_likes = int(request.form['min_likes']) if request.form['min_likes'] else None
        min_comments = int(request.form['min_comments']) if request.form['min_comments'] else None
        min_reposts = int(request.form['min_reposts']) if request.form['min_reposts'] else None
        min_views = int(request.form['min_views']) if request.form['min_views'] else None

        if all(v is None for v in [count, start_date, end_date, min_likes, min_comments, min_reposts, min_views]):
             count = 100
        # if count is None and any(
        #         v is not None for v in [start_date, end_date, min_likes, min_comments, min_reposts, min_views]):
        #     count = None


        sort_by = request.form['sort_by'] if request.form['sort_by'] else None
        sort_order = request.form['sort_order']

        # Использование сохраненного owner_id из DataStorage
        posts = vk_data_handler.get_wall_posts(-group_id, count, start_date, end_date, min_likes, min_comments, min_reposts, min_views, sort_by, sort_order)
        formatted_posts = []



        for post in posts:

            photo_urls = []

            # Проверяем наличие вложений в посте
            if 'attachments' in post:
                attachments = post['attachments']

                # Проходим по каждому вложению
                for attachment in attachments:
                    # Проверяем, является ли вложение фотографией
                    if attachment['type'] == 'photo':
                        # Извлекаем ссылку на фотографию нужного размера (в данном случае, самый большой)
                        photo_url = attachment['photo']['sizes'][-1]['url']
                        # Добавляем ссылку на фотографию в массив
                        photo_urls.append(photo_url)

            formatted_post = {
                'id': post['id'],
                'text': post['text'],
                'date': datetime.fromtimestamp(post['date']).strftime('%Y-%m-%d %H:%M:%S'),
                'likes_count': post['likes']['count'],
                'comments_count': post['comments']['count'],
                'reposts_count': post['reposts']['count'],
                'views_count': post['views']['count'] if 'views' in post else 'Unknown',
                'url_photos': photo_urls
            }

            formatted_posts.append(formatted_post)
    # Здесь вы можете использовать group_id для выполнения каких-либо действий или загрузки данных
    # Например, передать его в шаблон или использовать для извлечения записей из соответствующей группы
        DataStorage.clear_data()
        DataStorage.append_data(formatted_posts)
        print(DataStorage.formatted_data)
        return render_template('posts.html', posts=formatted_posts, group_id=group_id, count=count,
                           start_date=start_date_str,
                           end_date= end_date_str,
                           min_likes= min_likes,
                           min_comments=min_comments,
                           min_reposts=min_reposts,
                           min_views= min_views, sort_by=sort_by, sort_order=sort_order)
    else:
        return render_template('posts.html', group_id=group_id)




@app.route('/user/<int:user_id>/posts', methods=['GET', 'POST'])
def user_posts(user_id):
    if request.method == 'POST':
        print('Начало обработки POST запроса')
        print(user_id)
        print('Форма данных:', request.form)
        count = int(request.form['count']) if request.form['count'] else None
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d') if request.form['start_date'] else None
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d') if request.form['end_date'] else None
        start_date_str = start_date.strftime('%Y-%m-%d') if request.form['start_date'] else None
        end_date_str = end_date.strftime('%Y-%m-%d') if request.form['end_date'] else None
        min_likes = int(request.form['min_likes']) if request.form['min_likes'] else None
        min_comments = int(request.form['min_comments']) if request.form['min_comments'] else None
        min_reposts = int(request.form['min_reposts']) if request.form['min_reposts'] else None
        min_views = int(request.form['min_views']) if request.form['min_views'] else None

        if all(v is None for v in [count, start_date, end_date, min_likes, min_comments, min_reposts, min_views]):
             count = 100
        # if count is None and any(
        #         v is not None for v in [start_date, end_date, min_likes, min_comments, min_reposts, min_views]):
        #     count = None


        sort_by = request.form['sort_by'] if request.form['sort_by'] else None
        sort_order = request.form['sort_order']

        # Использование сохраненного owner_id из DataStorage
        posts = vk_data_handler.get_wall_posts(user_id, count, start_date, end_date, min_likes, min_comments, min_reposts, min_views, sort_by, sort_order)
        formatted_posts = []

        for post in posts:

            photo_urls = []

            # Проверяем наличие вложений в посте
            if 'attachments' in post:
                attachments = post['attachments']

                # Проходим по каждому вложению
                for attachment in attachments:
                    # Проверяем, является ли вложение фотографией
                    if attachment['type'] == 'photo':
                        # Извлекаем ссылку на фотографию нужного размера (в данном случае, самый большой)
                        photo_url = attachment['photo']['sizes'][-1]['url']
                        # Добавляем ссылку на фотографию в массив
                        photo_urls.append(photo_url)

            formatted_post = {
                'id': post['id'],
                'text': post['text'],
                'date': datetime.fromtimestamp(post['date']).strftime('%Y-%m-%d %H:%M:%S'),
                'likes_count': post['likes']['count'],
                'comments_count': post['comments']['count'],
                'reposts_count': post['reposts']['count'],
                'views_count': post['views']['count'] if 'views' in post else 'Unknown',
                'url_photos': photo_urls
            }
            formatted_posts.append(formatted_post)

        # Здесь вы можете использовать user_id для выполнения каких-либо действий или загрузки данных
        # Например, передать его в шаблон или использовать для извлечения записей из соответствующего пользователя
        DataStorage.clear_data()
        DataStorage.append_data(formatted_posts)
        print(DataStorage.formatted_data)
        return render_template('posts.html', posts=formatted_posts, user_id=user_id, count=count,
                           start_date=start_date_str,
                           end_date=end_date_str,
                           min_likes=min_likes,
                           min_comments=min_comments,
                           min_reposts=min_reposts,
                           min_views=min_views, sort_by=sort_by, sort_order=sort_order)
    else:
        return render_template('posts.html', user_id=user_id)


@app.route('/user/<string:user_id>')
def get_user_info_route(user_id):
    user_info = vk_data_handler.get_user_info(user_id)
    if user_info['sex'] == 1:
        user_info['sex'] = 'женский'
    elif user_info['sex'] == 2:
        user_info['sex'] = 'мужской'
    if user_info['is_closed']:
        user_info['is_closed'] = 'закрытый'
    else:
        user_info['is_closed'] = 'открытый'
    if 'city' not in user_info:
        user_info['city'] = {'title': 'Нет информации о городе'}  # Устанавливаем значение по умолчанию
    if 'country' not in user_info:
        user_info['country'] = {'title': 'Нет информации о стране'}  # Устанавливаем значение по умолчанию
    print(user_info)
    if user_info and user_id != None:
        return render_template("result.html", user_info=user_info)
    else:
        error_msg = "Ошибка при получении информации о пользователе. Пожалуйста, проверьте ID пользователя."
        logging.error(error_msg)
        return error_msg

@app.route('/user_info', methods=['POST'])
def user_redirect():
    user_id = request.form.get("user_id") if request.form['user_id'] else None
    # Вместо простого перенаправления, вы можете выполнить дополнительные действия, такие как обработка данных и т.д.
    return redirect(url_for('get_user_info_route', user_id=user_id))

@app.route('/download_json')
def download_json():
    file_path = 'groups_data.json'
    DataExporter.save_to_json(DataStorage.formatted_data, file_path)
    return send_file(file_path, as_attachment=True)

@app.route('/download_posts_json')
def download_posts_json():
    file_path = 'groups_posts_data.json'
    DataExporter.save_posts_to_json(DataStorage.formatted_data, file_path)
    return send_file(file_path, as_attachment=True)

@app.route('/download_csv')
def download_csv():
    file_path = 'groups_data.csv'
    DataExporter.save_to_csv(DataStorage.formatted_data, file_path)
    return send_file(file_path, as_attachment=True)

@app.route('/download_posts_csv')
def download_posts_csv():
    file_path = 'groups_posts_data.csv'
    DataExporter.save_posts_to_csv(DataStorage.formatted_data, file_path)
    return send_file(file_path, as_attachment=True)

@app.route('/group/<group_id>')
def group_details(group_id):
    # Fetch detailed information about the group using the group_id
    group_info = vk_data_handler.get_group_info_by_id(group_id)
    DataStorage.owner_id = group_id
    if group_info:
        return render_template("group_details.html", group_info=group_info)
    else:
        error_msg = "Ошибка при получении информации о группе. Пожалуйста, проверьте ID группы."
        logging.error(error_msg)
        return error_msg



@app.route('/get_stats_for_period', methods=['POST'])
def get_stats_for_period():
    start_date = request.form.get('startDate')
    end_date = request.form.get('endDate')
    group_id = -int(request.form.get('groupId'))
    # Преобразовать строку в объект даты
    start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
    end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')

    # Преобразовать объекты даты в количество секунд с начала эпохи
    start_date_int = int(start_date_obj.timestamp())
    end_date_int = int(end_date_obj.timestamp())

    print(start_date)
    print(end_date)
    print(group_id)
    group_info = vk_data_handler.get_group_info_by_id(-group_id)
    total_subscribers = group_info['members_count']

    total_likes = 0
    total_comments = 0
    total_views = 0
    total_count = 0

    count = 100  # Устанавливаем количество записей для одного запроса
    offset = 0

    while True:
        # Получение записей на стене с учетом параметров count и offset
        wall_posts = vk_data_handler.vk.wall.get(owner_id=group_id, count=count, offset=offset, filter='all', extended=1)
        posts = wall_posts['items']

        # Если нет больше записей, выходим из цикла
        if not posts:
            break

        filtered_posts = [post for post in posts if start_date_int <= post['date'] <= end_date_int]

        # Если все записи в текущем запросе не соответствуют указанному периоду времени, завершаем цикл
        if not filtered_posts:
            break

        # Подсчет статистики
        for post in filtered_posts:
            total_likes += post['likes']['count']
            total_comments += post['comments']['count']
            total_views += post['views'].get('count', 0)  # Получаем значение по ключу 'count', если ключ отсутствует, возвращаем 0
            total_count += 1

        statistics = {
            'totalPosts': total_count,
            'totalLikes': total_likes,
            'totalComments': total_comments,
            'totalViews': total_views,
            'averageLikesPerPost':  round(total_likes / total_count),
            'averageCommentsPerPost': round(total_comments / total_count),
            'averageViewsPerPost': round(total_views / total_count),
            'engagementRate': ((total_likes + total_comments) / total_subscribers) * 100,
            'postEngagementRate': ((total_likes / total_count + total_comments / total_count) / total_subscribers) * 100,
        }
        print(offset)
        offset += count
    print(statistics)
        # Возвращаем данные статистики в виде JSON
    return jsonify(statistics)

@app.route('/get_groups', methods=['POST'])  # Принимаем POST запросы
def get_groups_route():
    try:
        # Получаем ID пользователя из запроса
        user_id = request.json.get('user_id')
        # Вызываем вашу функцию get_groups для получения данных о группах
        data = vk_data_handler.get_user_groups(user_id)
        # Возвращаем результат в формате JSON
        return jsonify(data)
    except Exception as e:
        logging.error(f"Ошибка при обработке запроса: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/group_details', methods=['POST'])
def group_redirect():
    group_id = request.form['group_id']
    # Вместо простого перенаправления, вы можете выполнить дополнительные действия, такие как обработка данных и т.д.
    return redirect(url_for('group_details', group_id=group_id))


if __name__ == '__main__':
    vk_data_handler = VKDataHandler("vk1.a.1_Xz5kUUFw8CX88ZfIJS3_a8oZlgCYqYV-6kozs42ZLUVivaBrFVgkmdJR0xuV7Yjj-KIHkRHTg5nIR2idJw1yMepBBggkPiiZRG6T1MOAeNklVcqaqMjdwUQjuBSrz1YnLYmvyoVM2L8RaGzTENlB3kyRqOAl3NXbWmR_Yz4tFPEYAIbK7YF8O0V_TNGJYtZwBhjaGsbtMvUr8a63nNIg")
    app.run(debug=True)
