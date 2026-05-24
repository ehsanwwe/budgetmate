from datetime import date


def _is_leap_jalali(year: int) -> bool:
    leap_years = [1, 5, 9, 13, 17, 22, 26, 30]
    return ((year - 474) % 2820 + 474 + 38) * 682 % 2816 < 682


def _jalali_to_gregorian(jy: int, jm: int, jd: int):
    jy += 1595
    days = -355779 + (365 + _is_leap_jalali(jy)) * (jy // 2820 * 2820) + \
           (365 + _is_leap_jalali(jy % 2820 + 474)) * ((jy % 2820) // 4 * 4) + \
           (365 + _is_leap_jalali(jy % 4 + (jy % 2820) // 4 * 4)) * (jy % 4) + \
           (30 * jm - (jm - (1 if jm <= 6 else 7))) + jd
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    return gy, days


def gregorian_to_jalali(gy: int, gm: int, gd: int):
    g_d_no = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400
    for i in range(gm - 1):
        g_d_no += [31, 29 if gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0) else 28,
                   31, 30, 31, 30, 31, 31, 30, 31, 30, 31][i]
    g_d_no += gd - 1

    j_d_no = g_d_no - 79

    j_np = j_d_no // 12053
    j_d_no %= 12053

    jy = 979 + 33 * j_np + 4 * (j_d_no // 1461)
    j_d_no %= 1461

    if j_d_no >= 366:
        jy += (j_d_no - 1) // 365
        j_d_no = (j_d_no - 1) % 365

    for i, days in enumerate([0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]):
        if j_d_no >= days:
            jm = i + 1

    jd = j_d_no - [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334][jm - 1] + 1
    return jy, jm, jd


def current_jalali_month() -> tuple[int, int]:
    today = date.today()
    jy, jm, _ = gregorian_to_jalali(today.year, today.month, today.day)
    return jm, jy
