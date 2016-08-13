# coding=utf-8
import random

__doc__ = """
Нужно отправлять посты таким образом:
1) От N штук в неделю до N'
2) Чтобы каждый пост был разбавлен шумовыми. Вопрос про количество шумовых между? Мне кажется, это тоже должен быть
рандом, только не менее чего-то и не более чего-то.
3) Каждый день должен быть рандом. Но в сумее - недельный рандом. Нужно выводить это как-то.
4*) На праздниках, либо в определенные дни должны быть затишья.
5*) Должны быть затишья и наоборот подъемы глобальные. То есть, предусмотреть что чувак будет
ходить в продолжительный отпуск.
"""

DAYS_IN_WEEK = 7


def create_posts_sequence(n_min, n_max=None, pass_count=10):
    result = [0] * DAYS_IN_WEEK
    _n_max = n_max or n_min
    creator = (n_min + _n_max) / (2. * DAYS_IN_WEEK)
    adder = 0
    prev_adder = 0
    for passage in range(pass_count):
        for day_number in range(DAYS_IN_WEEK):
            if result[day_number] == 0:
                day_count = random.randint(
                    int(-(creator / 4)),
                    int(creator + creator / 2)
                )
            else:
                day_count = result[day_number]

            if adder != 0:
                day_count += int(random.random() * adder)

            if day_count < 0:
                day_count = 0

            result[day_number] = day_count

        week_count = sum(result)
        if week_count <= _n_max and week_count >= n_min:
            return result
        elif week_count > _n_max:
            adder = float(_n_max - week_count) / DAYS_IN_WEEK
        elif week_count < n_min:
            adder = float((n_min - week_count) * 3) / DAYS_IN_WEEK

        if adder == prev_adder:
            return result
        else:
            prev_adder = adder
    return result


if __name__ == '__main__':
    res = create_posts_sequence(70, pass_count=50)
    print sum(res), res
