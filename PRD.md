# PRD: Астрологический MCP Сервер (astro-mcp)

**Версия:** 1.0.0  
**Дата:** 22 февраля 2026  
**Статус:** Draft  

---

## Содержание

1. [Overview](#1-overview)
2. [Stakeholders & Use Cases](#2-stakeholders--use-cases)
3. [Functional Requirements](#3-functional-requirements)
4. [Technical Architecture](#4-technical-architecture)
5. [Data Models](#5-data-models)
6. [LLM Output Optimization](#6-llm-output-optimization)
7. [Rectification Algorithm](#7-rectification-algorithm)
8. [Non-Functional Requirements](#8-non-functional-requirements)
9. [Dependencies & Installation](#9-dependencies--installation)
10. [Testing Strategy](#10-testing-strategy)
11. [Future Enhancements](#11-future-enhancements)

---

## 1. Overview

### Описание проекта

`astro-mcp` — MCP (Model Context Protocol) сервер на Python, предоставляющий астрологическому LLM-агенту набор высокоточных инструментов для расчёта и интерпретации астрологических данных. Сервер выступает как «астрологический вычислительный движок» для автономного агента: агент принимает запросы на естественном языке, вызывает нужные инструменты и формирует развёрнутые интерпретации.

### Цели

- Обеспечить точность расчётов профессионального уровня (Swiss Ephemeris, погрешность < 1")
- Минимизировать объём токенов в ответах (оптимизация под LLM-контекст)
- Поддержать полный спектр техник западной тропической астрологии
- Обеспечить бесшовную интеграцию с Claude Desktop и любым MCP-совместимым клиентом
- Поддержать три системы домов: Placidus (по умолчанию), Whole Sign, Koch

### Системная астрология

| Параметр | Значение |
|---|---|
| Зодиак | Тропический (западный) |
| Система домов (default) | Placidus |
| Дополнительные системы домов | Whole Sign, Koch |
| Небесные тела | 10 планет + 5 астероидов + Лунные узлы + Часть Фортуны + углы |
| Аспекты | Мажорные (0°, 60°, 90°, 120°, 180°) + минорные (30°, 45°, 135°, 150°, 72°, 144°) |

---

## 2. Stakeholders & Use Cases

### Стейкхолдеры

| Роль | Описание |
|---|---|
| **End User (B2C)** | Клиент, получающий астрологическую консультацию через чат с агентом |
| **Practitioner (B2B)** | Профессиональный астролог, использующий агента как рабочий инструмент |
| **Personal User** | Пользователь личного астрологического дневника/трекера |
| **LLM Agent** | Прямой потребитель MCP-инструментов (Claude, GPT-4 и др.) |
| **MCP Client** | Claude Desktop, любое MCP-совместимое приложение |

### Сценарии использования

#### UC-01: Консультация по натальной карте (B2C)
```
Клиент → Агент: "Расскажи о моей натальной карте. 
Я родился 15 марта 1990, 14:30, Москва."
Агент → MCP: calculate_natal_chart(...)
MCP → Агент: {полная карта в компактном JSON}
Агент → Клиент: [развёрнутая интерпретация]
```

#### UC-02: Анализ текущих транзитов (B2C / Personal)
```
Клиент → Агент: "Какие транзиты влияют на меня сейчас?"
Агент → MCP: calculate_natal_chart(...) + calculate_transits(today)
MCP → Агент: {транзиты с точными датами аспектов}
Агент → Клиент: [прогноз на период]
```

#### UC-03: Ректификация (B2B — профессиональный инструмент)
```
Астролог → Агент: "Уточни время рождения. 
Примерно 08:00-10:00. События: развод 2015-03-12, 
повышение 2018-09-01, рождение ребёнка 2020-05-15"
Агент → MCP: calculate_rectification_hints(...)
MCP → Агент: {рейтинг вариантов времени с корреляциями}
Агент → Астролог: [детальный анализ]
```

#### UC-04: Синастрия пары (B2C)
```
Клиент → Агент: "Мы с партнёром совместимы? 
Я: 15.03.1990 14:30 Москва. Он: 22.07.1988 09:00 СПб"
Агент → MCP: calculate_synastry(person1, person2)
MCP → Агент: {межличностные аспекты, домовые наложения}
Агент → Клиент: [анализ совместимости]
```

#### UC-05: Ежемесячный лунный прогноз (Personal)
```
Пользователь → Агент: "Когда мой следующий лунар и что он означает?"
Агент → MCP: calculate_lunar_return(natal_data, current_date)
MCP → Агент: {дата + карта лунара}
Агент → Пользователь: [прогноз на лунный месяц]
```

---

## 3. Functional Requirements

### 3.1 Общие параметры инструментов

Все инструменты принимают необязательный параметр `house_system` (enum: `"P"` — Placidus, `"W"` — Whole Sign, `"K"` — Koch; default: `"P"`) и `degree_format` (enum: `"dms"` — градусы/минуты/секунды, `"dec"` — десятичные градусы; default: `"dms"`).

---

### Tool 1: `calculate_natal_chart`

**Описание:** Расчёт полной натальной карты. Основной инструмент, результат которого используется как входные данные для большинства остальных инструментов.

#### Input Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["date", "time", "location"],
  "properties": {
    "date": {
      "type": "string",
      "format": "date",
      "description": "Дата рождения в формате YYYY-MM-DD",
      "example": "1990-03-15"
    },
    "time": {
      "type": "string",
      "pattern": "^([01]\\d|2[0-3]):[0-5]\\d(:[0-5]\\d)?$",
      "description": "Время рождения в формате HH:MM или HH:MM:SS (local time)",
      "example": "14:30"
    },
    "location": {
      "oneOf": [
        {
          "type": "string",
          "description": "Название города (геокодируется автоматически)",
          "example": "Moscow, Russia"
        },
        {
          "type": "object",
          "required": ["lat", "lon"],
          "properties": {
            "lat": {"type": "number", "minimum": -90, "maximum": 90},
            "lon": {"type": "number", "minimum": -180, "maximum": 180},
            "tz": {"type": "string", "description": "IANA timezone, напр. Europe/Moscow"}
          }
        }
      ]
    },
    "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"},
    "degree_format": {"type": "string", "enum": ["dms","dec"], "default": "dms"},
    "include_asteroids": {"type": "boolean", "default": true},
    "include_arabic_parts": {"type": "boolean", "default": false}
  }
}
```

#### Output Schema

```json
{
  "type": "object",
  "properties": {
    "meta": {
      "type": "object",
      "properties": {
        "dt": {"type": "string", "description": "UTC datetime ISO8601"},
        "loc": {"type": "object", "properties": {"lat": {}, "lon": {}, "tz": {}, "name": {}}},
        "hs": {"type": "string", "description": "house system code"},
        "jd": {"type": "number", "description": "Julian Day Number"}
      }
    },
    "planets": {
      "type": "object",
      "description": "Планеты, ключ — короткий код планеты",
      "additionalProperties": {"$ref": "#/definitions/ChartPoint"}
    },
    "angles": {
      "type": "object",
      "properties": {
        "Asc": {"$ref": "#/definitions/ChartPoint"},
        "MC":  {"$ref": "#/definitions/ChartPoint"},
        "Dsc": {"$ref": "#/definitions/ChartPoint"},
        "IC":  {"$ref": "#/definitions/ChartPoint"}
      }
    },
    "houses": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "n": {"type": "integer", "minimum": 1, "maximum": 12},
          "cusp": {"type": "string"},
          "sign": {"type": "string"},
          "ruler": {"type": "string", "description": "планетарный управитель (классический)"},
          "mod_ruler": {"type": "string", "description": "современный управитель, если отличается"}
        }
      }
    },
    "aspects": {
      "type": "array",
      "items": {"$ref": "#/definitions/Aspect"}
    }
  }
}
```

#### Пример компактного вывода

```json
{
  "meta":{"dt":"1990-03-15T11:30:00Z","loc":{"lat":55.75,"lon":37.62,"tz":"Europe/Moscow","name":"Moscow"},"hs":"P","jd":2447965.98},
  "planets":{
    "Su":{"lon":"24°45'12\"","sign":"Pis","deg":24.75,"house":9,"R":false},
    "Mo":{"lon":"18°32'44\"","sign":"Sag","deg":18.55,"house":6,"R":false},
    "Me":{"lon":"07°11'02\"","sign":"Pis","deg":7.18,"house":9,"R":false},
    "Ve":{"lon":"16°22'15\"","sign":"Tau","deg":16.37,"house":11,"R":false},
    "Ma":{"lon":"12°58'31\"","sign":"Cap","deg":12.97,"house":7,"R":false},
    "Ju":{"lon":"05°44'18\"","sign":"Can","deg":5.74,"house":1,"R":false},
    "Sa":{"lon":"23°10'05\"","sign":"Cap","deg":23.17,"house":7,"R":false},
    "Ur":{"lon":"08°51'22\"","sign":"Cap","deg":8.86,"house":7,"R":false},
    "Ne":{"lon":"13°33'48\"","sign":"Cap","deg":13.56,"house":7,"R":false},
    "Pl":{"lon":"16°15'09\"","sign":"Sco","deg":16.25,"house":5,"R":false},
    "Ch":{"lon":"27°03'54\"","sign":"Can","deg":27.07,"house":2,"R":false},
    "NN":{"lon":"11°44'00\"","sign":"Aqu","deg":11.73,"house":8,"R":true},
    "SN":{"lon":"11°44'00\"","sign":"Leo","deg":11.73,"house":2,"R":true}
  },
  "angles":{
    "Asc":{"lon":"00°12'33\"","sign":"Can","deg":0.21},
    "MC":{"lon":"07°55'19\"","sign":"Pis","deg":7.92},
    "Dsc":{"lon":"00°12'33\"","sign":"Cap","deg":0.21},
    "IC":{"lon":"07°55'19\"","sign":"Vir","deg":7.92}
  },
  "houses":[
    {"n":1,"cusp":"00°12'Can","sign":"Can","ruler":"Mo","mod_ruler":"Mo"},
    {"n":2,"cusp":"21°44'Can","sign":"Can","ruler":"Mo","mod_ruler":"Mo"},
    {"n":3,"cusp":"13°02'Leo","sign":"Leo","ruler":"Su","mod_ruler":"Su"},
    {"n":4,"cusp":"07°55'Vir","sign":"Vir","ruler":"Me","mod_ruler":"Me"},
    {"n":5,"cusp":"09°11'Lib","sign":"Lib","ruler":"Ve","mod_ruler":"Ve"},
    {"n":6,"cusp":"16°22'Sco","sign":"Sco","ruler":"Ma","mod_ruler":"Pl"},
    {"n":7,"cusp":"00°12'Cap","sign":"Cap","ruler":"Sa","mod_ruler":"Sa"},
    {"n":8,"cusp":"21°44'Cap","sign":"Cap","ruler":"Sa","mod_ruler":"Sa"},
    {"n":9,"cusp":"13°02'Aqu","sign":"Aqu","ruler":"Sa","mod_ruler":"Ur"},
    {"n":10,"cusp":"07°55'Pis","sign":"Pis","ruler":"Ju","mod_ruler":"Ne"},
    {"n":11,"cusp":"09°11'Ari","sign":"Ari","ruler":"Ma","mod_ruler":"Ma"},
    {"n":12,"cusp":"16°22'Tau","sign":"Tau","ruler":"Ve","mod_ruler":"Ve"}
  ],
  "aspects":[
    {"p1":"Su","p2":"Mo","asp":"Squ","orb":6.20,"apply":false},
    {"p1":"Su","p2":"Ju","asp":"Tri","orb":0.99,"apply":false},
    {"p1":"Mo","p2":"Ju","asp":"Cnj","orb":7.19,"apply":false},
    {"p1":"Ve","p2":"Pl","asp":"Cnj","orb":0.12,"apply":false},
    {"p1":"Ma","p2":"Sa","asp":"Cnj","orb":10.20,"apply":false},
    {"p1":"Ma","p2":"Ur","asp":"Cnj","orb":4.11,"apply":false},
    {"p1":"Ma","p2":"Ne","asp":"Cnj","orb":0.99,"apply":false}
  ]
}
```

#### Ошибки и edge cases

| Код ошибки | Условие | Описание |
|---|---|---|
| `GEOCODE_FAILED` | Город не найден | Запросить координаты вручную |
| `TIMEZONE_UNKNOWN` | TZ не определён | Запросить часовой пояс у пользователя |
| `TIME_UNKNOWN` | Время не предоставлено | Рассчитать без домов (только планеты) |
| `INVALID_DATE` | Дата вне диапазона Swiss Ephemeris | Диапазон: 13200 до н.э. — 17191 н.э. |
| `POLAR_LOCATION` | Широта > 66.5° | Система Placidus невозможна, переключить на Whole Sign |

---

### Tool 2: `calculate_transits`

**Описание:** Расчёт транзитных планет на заданную дату или период, их аспекты к натальным планетам, точные даты аспектов.

#### Input Schema

```json
{
  "type": "object",
  "required": ["natal", "transit_date"],
  "properties": {
    "natal": {
      "description": "Вывод calculate_natal_chart или краткие натальные данные",
      "oneOf": [
        {"$ref": "#/definitions/NatalChartRef"},
        {"$ref": "#/definitions/BirthData"}
      ]
    },
    "transit_date": {
      "type": "string",
      "format": "date",
      "description": "Дата транзита (YYYY-MM-DD). Если задан period — начальная дата"
    },
    "period_days": {
      "type": "integer",
      "minimum": 1,
      "maximum": 3650,
      "description": "Длина периода в днях (если нужен диапазон, не одна дата)"
    },
    "transit_location": {
      "description": "Место для расчёта транзитных домов (опционально)",
      "oneOf": [
        {"type": "string"},
        {"type": "object", "properties": {"lat": {}, "lon": {}}}
      ]
    },
    "orbs": {
      "type": "object",
      "description": "Переопределение орбисов для каждого типа аспекта",
      "example": {"Cnj": 8, "Opp": 8, "Tri": 7, "Squ": 7, "Sex": 5}
    },
    "fast_planets_only": {
      "type": "boolean",
      "default": false,
      "description": "Только Луна, Меркурий, Венера, Марс (для суточных прогнозов)"
    },
    "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"}
  }
}
```

#### Output Schema & Пример

```json
{
  "date":"2024-06-15",
  "transit_planets":{
    "Su":{"lon":"24°33'Gem","deg":84.56,"house":12,"R":false},
    "Mo":{"lon":"08°12'Sco","deg":218.20,"house":5,"R":false},
    "Sa":{"lon":"18°55'Pis","deg":348.92,"house":9,"R":false}
  },
  "aspects":[
    {"tp":"Su","np":"Me","asp":"Squ","orb":0.45,"apply":true,"exact":"2024-06-16"},
    {"tp":"Sa","np":"Su","asp":"Cnj","orb":5.82,"apply":false,"exact":"2024-04-01"},
    {"tp":"Sa","np":"Me","asp":"Cnj","orb":5.64,"apply":false,"exact":null},
    {"tp":"Ne","np":"MC","asp":"Cnj","orb":2.14,"apply":true,"exact":"2025-03-10"}
  ]
}
```

#### Ошибки и edge cases

| Код ошибки | Условие |
|---|---|
| `PERIOD_TOO_LONG` | `period_days` > 3650 |
| `NATAL_MISSING` | Натальные данные не переданы |
| `EXACT_DATE_NOT_FOUND` | Аспект не точнеет в заданный период (уже прошёл/будет только после) |

---

### Tool 3: `calculate_secondary_progressions`

**Описание:** Вторичные прогрессии методом «день за год». Каждый день после рождения соответствует одному году жизни.

#### Input Schema

```json
{
  "type": "object",
  "required": ["natal", "progression_date"],
  "properties": {
    "natal": {"$ref": "#/definitions/BirthData"},
    "progression_date": {
      "type": "string",
      "format": "date",
      "description": "Дата, на которую рассчитываются прогрессии"
    },
    "include_solar_arc": {
      "type": "boolean",
      "default": false,
      "description": "Добавить расчёт Солнечной Дуги"
    },
    "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"}
  }
}
```

#### Output Schema & Пример

```json
{
  "prog_date":"2024-06-15",
  "prog_age":34.25,
  "prog_day":"1990-04-14",
  "prog_planets":{
    "Su":{"lon":"19°01'Ari","deg":19.02,"sign":"Ari","R":false},
    "Mo":{"lon":"14°44'Lib","deg":194.73,"sign":"Lib","R":false},
    "Asc":{"lon":"22°33'Leo","deg":142.55,"sign":"Leo"},
    "MC":{"lon":"04°18'Tau","deg":34.30,"sign":"Tau"}
  },
  "prog_to_natal_aspects":[
    {"pp":"Su","np":"Ve","asp":"Sex","orb":0.37,"apply":false},
    {"pp":"Mo","np":"Sa","asp":"Opp","orb":1.22,"apply":true},
    {"pp":"Asc","np":"Ju","asp":"Tri","orb":0.61,"apply":false}
  ],
  "prog_to_prog_aspects":[
    {"p1":"Su","p2":"Mo","asp":"Sex","orb":2.15}
  ]
}
```

---

### Tool 4: `calculate_solar_return`

**Описание:** Солнечное возвращение — момент, когда транзитное Солнце возвращается на точную натальную позицию Солнца.

#### Input Schema

```json
{
  "type": "object",
  "required": ["natal", "year"],
  "properties": {
    "natal": {"$ref": "#/definitions/BirthData"},
    "year": {
      "type": "integer",
      "description": "Год, для которого строится соляр",
      "example": 2024
    },
    "return_location": {
      "description": "Место соляра (если клиент в другой локации в ДР — 'relocation solar return')",
      "oneOf": [
        {"type": "string", "description": "Название города"},
        {"type": "object", "properties": {"lat": {}, "lon": {}}}
      ]
    },
    "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"}
  }
}
```

#### Output Schema & Пример

```json
{
  "return_dt":"2024-03-15T08:44:22Z",
  "return_loc":{"lat":55.75,"lon":37.62,"name":"Moscow"},
  "sr_planets":{
    "Su":{"lon":"24°45'Pis","deg":354.75,"house":10,"R":false},
    "Mo":{"lon":"03°21'Tau","deg":33.35,"house":11,"R":false},
    "Asc":{"lon":"12°33'Gem","deg":72.55}
  },
  "sr_houses":[
    {"n":1,"cusp":"12°33'Gem"},
    {"n":10,"cusp":"24°12'Pis"}
  ],
  "sr_to_natal_aspects":[
    {"sp":"Mo","np":"Ju","asp":"Cnj","orb":1.20},
    {"sp":"Ve","np":"Asc","asp":"Tri","orb":0.85}
  ]
}
```

---

### Tool 5: `calculate_rectification_hints`

**Описание:** Анализ вариантов времени рождения на основе корреляции жизненных событий с астрологическими техниками. Подробный алгоритм описан в разделе 7.

#### Input Schema

```json
{
  "type": "object",
  "required": ["birth_data", "events"],
  "properties": {
    "birth_data": {
      "type": "object",
      "required": ["date", "location"],
      "properties": {
        "date": {"type": "string", "format": "date"},
        "time_from": {"type": "string", "description": "Начало диапазона HH:MM"},
        "time_to": {"type": "string", "description": "Конец диапазона HH:MM"},
        "time_step_min": {
          "type": "integer",
          "default": 4,
          "minimum": 1,
          "maximum": 30,
          "description": "Шаг перебора в минутах (4 мин ≈ 1° ASC)"
        },
        "location": {"oneOf": [{"type": "string"}, {"type": "object"}]}
      }
    },
    "events": {
      "type": "array",
      "minItems": 3,
      "items": {
        "type": "object",
        "required": ["date", "type"],
        "properties": {
          "date": {"type": "string", "format": "date"},
          "type": {
            "type": "string",
            "enum": [
              "marriage","divorce","birth_child","death_close","career_rise",
              "career_fall","relocation","accident","illness_major","surgery",
              "financial_gain","financial_loss","education","spiritual_shift","other"
            ]
          },
          "description": {"type": "string"},
          "date_accuracy": {"type": "string", "enum": ["exact","month","year"], "default": "exact"}
        }
      }
    },
    "techniques": {
      "type": "array",
      "items": {"type": "string", "enum": ["transits","progressions","profections","solar_arc","all"]},
      "default": ["transits","progressions","profections"]
    },
    "top_n": {
      "type": "integer",
      "default": 5,
      "description": "Количество лучших вариантов в ответе"
    }
  }
}
```

#### Output Schema & Пример

```json
{
  "candidates":[
    {
      "time":"09:44",
      "score":87.5,
      "Asc":"14°22'Can",
      "MC":"24°11'Pis",
      "correlations":[
        {
          "event_date":"2015-03-12",
          "event_type":"divorce",
          "technique":"transits",
          "indicators":[
            {"planet":"Sa","asp":"Cnj","point":"DSC","orb":0.34},
            {"planet":"Pl","asp":"Squ","point":"Ve","orb":1.22}
          ],
          "score":9.2
        },
        {
          "event_date":"2018-09-01",
          "event_type":"career_rise",
          "technique":"progressions",
          "indicators":[
            {"planet":"Su","asp":"Cnj","point":"MC","orb":0.55}
          ],
          "score":8.8
        }
      ]
    },
    {
      "time":"09:48",
      "score":74.1,
      "Asc":"15°33'Can",
      "MC":"25°22'Pis",
      "correlations":[]
    }
  ],
  "best_time":"09:44",
  "confidence":"medium",
  "note":"Score based on 3 techniques, 5 events. Confidence: medium (≥3 strong correlations)"
}
```

#### Ошибки и edge cases

| Код ошибки | Условие |
|---|---|
| `TOO_FEW_EVENTS` | Менее 3 событий с известными датами |
| `RANGE_TOO_WIDE` | Диапазон > 6 часов (производительность) |
| `NO_CANDIDATES` | Ни один вариант не набрал score > 30 |

---

### Tool 6: `calculate_lunar_return`

**Описание:** Лунное возвращение — момент, когда транзитная Луна возвращается на точную натальную позицию Луны.

#### Input Schema

```json
{
  "type": "object",
  "required": ["natal"],
  "properties": {
    "natal": {"$ref": "#/definitions/BirthData"},
    "from_date": {
      "type": "string",
      "format": "date",
      "description": "Дата, начиная с которой искать следующий лунар (default: today)"
    },
    "count": {
      "type": "integer",
      "default": 1,
      "maximum": 12,
      "description": "Количество лунных возвращений для расчёта"
    },
    "return_location": {
      "description": "Место (если отличается от натального)",
      "oneOf": [{"type": "string"}, {"type": "object"}]
    },
    "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"}
  }
}
```

#### Output Schema & Пример

```json
{
  "returns":[
    {
      "return_dt":"2024-06-22T03:17:44Z",
      "return_loc":{"lat":55.75,"lon":37.62},
      "lr_planets":{
        "Mo":{"lon":"18°32'Sag","deg":258.55,"house":7},
        "Su":{"lon":"00°52'Can","deg":90.87,"house":2},
        "Asc":{"lon":"22°15'Sco","deg":232.25}
      },
      "lr_houses":[
        {"n":1,"cusp":"22°15'Sco"},
        {"n":7,"cusp":"22°15'Tau"}
      ]
    }
  ]
}
```

---

### Tool 7: `calculate_synastry`

**Описание:** Синастрия двух карт — анализ межличностных аспектов и наложение домов.

#### Input Schema

```json
{
  "type": "object",
  "required": ["person1", "person2"],
  "properties": {
    "person1": {"$ref": "#/definitions/BirthData"},
    "person2": {"$ref": "#/definitions/BirthData"},
    "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"},
    "orbs": {
      "type": "object",
      "description": "Орбисы для синастрических аспектов (обычно уменьшают на 1-2°)",
      "example": {"Cnj": 7, "Opp": 7, "Tri": 6, "Squ": 6, "Sex": 4}
    }
  }
}
```

#### Output Schema & Пример

```json
{
  "p1_label":"Person1",
  "p2_label":"Person2",
  "aspects":[
    {"p1_planet":"Su","p2_planet":"Mo","asp":"Cnj","orb":2.11,"harmony":true},
    {"p1_planet":"Ve","p2_planet":"Ma","asp":"Sex","orb":1.33,"harmony":true},
    {"p1_planet":"Sa","p2_planet":"Mo","asp":"Squ","orb":0.88,"harmony":false},
    {"p1_planet":"Ju","p2_planet":"Asc","asp":"Cnj","orb":3.21,"harmony":true}
  ],
  "house_overlays":{
    "p1_planets_in_p2_houses":{
      "Su":5,"Mo":8,"Ve":11,"Ma":7
    },
    "p2_planets_in_p1_houses":{
      "Su":3,"Mo":12,"Ve":1,"Ma":6
    }
  },
  "davison_dt":"1989-05-22T11:45:00Z",
  "compatibility_indicators":{
    "harmony_score":7.4,
    "tension_score":3.2,
    "strong_links":["Su-Mo Cnj","Ve-Ma Sex"],
    "challenges":["Sa-Mo Squ"]
  }
}
```

---

### Tool 8: `calculate_composite_chart`

**Описание:** Композитная карта методом средних точек — символическая карта пары/отношений.

#### Input Schema

```json
{
  "type": "object",
  "required": ["person1", "person2"],
  "properties": {
    "person1": {"$ref": "#/definitions/BirthData"},
    "person2": {"$ref": "#/definitions/BirthData"},
    "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"},
    "method": {
      "type": "string",
      "enum": ["midpoint","davison"],
      "default": "midpoint",
      "description": "midpoint — средние точки планет; davison — карта средней даты/времени"
    }
  }
}
```

#### Output Schema & Пример

```json
{
  "method":"midpoint",
  "comp_planets":{
    "Su":{"lon":"16°14'Aqu","deg":316.24,"house":8,"R":false},
    "Mo":{"lon":"03°33'Vir","deg":153.55,"house":1,"R":false},
    "Ve":{"lon":"19°28'Pis","deg":349.47,"house":9,"R":false}
  },
  "comp_angles":{
    "Asc":{"lon":"05°22'Vir","deg":155.37},
    "MC":{"lon":"03°44'Gem","deg":63.73}
  },
  "comp_houses":[
    {"n":1,"cusp":"05°22'Vir","sign":"Vir"},
    {"n":7,"cusp":"05°22'Pis","sign":"Pis"}
  ],
  "comp_aspects":[
    {"p1":"Su","p2":"Mo","asp":"Sex","orb":2.69},
    {"p1":"Ve","p2":"Ne","asp":"Cnj","orb":0.44}
  ]
}
```

---

### Tool 9: `calculate_profections`

**Описание:** Годовые профекции — эллинистическая техника. Каждый год жизни «профицирует» Асцендент на один знак (30°), определяя управителя года.

#### Input Schema

```json
{
  "type": "object",
  "required": ["natal", "target_date"],
  "properties": {
    "natal": {"$ref": "#/definitions/BirthData"},
    "target_date": {
      "type": "string",
      "format": "date",
      "description": "Дата, для которой определяется профекция (обычно день рождения или любая дата в даннном году жизни)"
    },
    "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"}
  }
}
```

#### Output Schema & Пример

```json
{
  "age":34,
  "profected_asc":"11th house",
  "profected_sign":"Tau",
  "year_ruler":"Ve",
  "year_ruler_natal_pos":{"lon":"16°22'Tau","house":11,"sign":"Tau"},
  "year_ruler_transit_pos":{"lon":"09°44'Tau","sign":"Tau","R":false},
  "activated_houses":[1,5,7,11],
  "activated_planets":["Ve","Mo"],
  "note":"Year lord Venus is activated. Themes: house 11 topics (social, gains, friends)"
}
```

---

### Tool 10: `get_planetary_hours`

**Описание:** Расчёт планетарных часов на заданный день. Часы разделены на дневные (восход–закат) и ночные (закат–восход) дуги, по 12 в каждой.

#### Input Schema

```json
{
  "type": "object",
  "required": ["date", "location"],
  "properties": {
    "date": {"type": "string", "format": "date"},
    "location": {
      "oneOf": [{"type": "string"}, {"type": "object", "properties": {"lat": {}, "lon": {}}}]
    },
    "tz_output": {
      "type": "string",
      "description": "IANA Timezone для вывода времён (default: timezone места)"
    }
  }
}
```

#### Output Schema & Пример

```json
{
  "date":"2024-06-15",
  "weekday":"Saturday",
  "day_ruler":"Sa",
  "sunrise":"04:45",
  "sunset":"21:33",
  "tz":"Europe/Moscow",
  "day_hours":[
    {"n":1,"planet":"Sa","start":"04:45","end":"05:59"},
    {"n":2,"planet":"Ju","start":"05:59","end":"07:13"},
    {"n":3,"planet":"Ma","start":"07:13","end":"08:27"},
    {"n":4,"planet":"Su","start":"08:27","end":"09:41"},
    {"n":5,"planet":"Ve","start":"09:41","end":"10:55"},
    {"n":6,"planet":"Me","start":"10:55","end":"12:09"},
    {"n":7,"planet":"Mo","start":"12:09","end":"13:23"},
    {"n":8,"planet":"Sa","start":"13:23","end":"14:38"},
    {"n":9,"planet":"Ju","start":"14:38","end":"15:52"},
    {"n":10,"planet":"Ma","start":"15:52","end":"17:06"},
    {"n":11,"planet":"Su","start":"17:06","end":"18:20"},
    {"n":12,"planet":"Ve","start":"18:20","end":"21:33"}
  ],
  "night_hours":[
    {"n":1,"planet":"Me","start":"21:33","end":"22:41"},
    {"n":2,"planet":"Mo","start":"22:41","end":"23:49"}
  ]
}
```

---

### Tool 11: `calculate_arabic_parts`

**Описание:** Арабские (лотовые) части — точки чувствительности, вычисляемые по формулам. Учитывается дневная/ночная карта.

#### Поддерживаемые части

| Код | Название | Формула (дневная) | Формула (ночная) |
|---|---|---|---|
| `FortPt` | Часть Фортуны | ASC + Mo - Su | ASC + Su - Mo |
| `SpiritPt` | Часть Духа | ASC + Su - Mo | ASC + Mo - Su |
| `MarriagePt` | Часть Брака | ASC + DSC - Ve | ASC + DSC - Ve |
| `DeathPt` | Часть Смерти | ASC + 8th cusp - Mo | ASC + 8th cusp - Sa |
| `ChildrenPt` | Часть Детей | ASC + Ju - Sa | ASC + Sa - Ju |
| `CareerPt` | Часть Карьеры | MC + Mo - Su | MC + Su - Mo |
| `TravelPt` | Часть Путешествий | ASC + 9th cusp - Ju | ASC + 9th cusp - Sa |

#### Input Schema

```json
{
  "type": "object",
  "required": ["natal"],
  "properties": {
    "natal": {
      "description": "Результат calculate_natal_chart или natla birth data",
      "oneOf": [{"$ref": "#/definitions/NatalChartFull"}, {"$ref": "#/definitions/BirthData"}]
    },
    "parts": {
      "type": "array",
      "items": {"type": "string", "enum": ["FortPt","SpiritPt","MarriagePt","DeathPt","ChildrenPt","CareerPt","TravelPt","all"]},
      "default": ["all"]
    }
  }
}
```

#### Output Schema & Пример

```json
{
  "chart_type":"day",
  "parts":{
    "FortPt":{"lon":"09°11'Lib","sign":"Lib","deg":189.18,"house":5},
    "SpiritPt":{"lon":"10°19'Gem","sign":"Gem","deg":70.32,"house":12},
    "MarriagePt":{"lon":"22°44'Vir","sign":"Vir","deg":172.73,"house":4},
    "DeathPt":{"lon":"14°02'Cap","sign":"Cap","deg":284.03,"house":7},
    "ChildrenPt":{"lon":"21°33'Can","sign":"Can","deg":111.55,"house":2},
    "CareerPt":{"lon":"06°44'Tau","sign":"Tau","deg":36.73,"house":11},
    "TravelPt":{"lon":"18°11'Sag","sign":"Sag","deg":258.18,"house":6}
  }
}
```

---

### Tool 12: `get_ephemeris`

**Описание:** Таблица эфемерид — позиции планеты за заданный период с заданным шагом.

#### Input Schema

```json
{
  "type": "object",
  "required": ["planet", "date_from", "date_to"],
  "properties": {
    "planet": {
      "type": "string",
      "enum": ["Su","Mo","Me","Ve","Ma","Ju","Sa","Ur","Ne","Pl","Ch","Ce","Pa","Ju2","Ve2","NN","SN"],
      "description": "Код планеты"
    },
    "date_from": {"type": "string", "format": "date"},
    "date_to": {"type": "string", "format": "date"},
    "step": {
      "type": "string",
      "enum": ["1h","6h","12h","1d","7d","30d"],
      "default": "1d"
    },
    "output_tz": {"type": "string", "description": "Timezone для вывода (default: UTC)"},
    "include_speed": {"type": "boolean", "default": false, "description": "Добавить суточную скорость (°/day)"},
    "include_retrograde": {"type": "boolean", "default": true}
  }
}
```

#### Output Schema & Пример

```json
{
  "planet":"Sa",
  "date_from":"2024-01-01",
  "date_to":"2024-03-01",
  "step":"7d",
  "rows":[
    {"dt":"2024-01-01","lon":"03°01'Pis","deg":333.02,"R":false,"speed":0.11},
    {"dt":"2024-01-08","lon":"04°44'Pis","deg":334.73,"R":false,"speed":0.10},
    {"dt":"2024-01-15","lon":"06°21'Pis","deg":336.35,"R":false,"speed":0.09},
    {"dt":"2024-01-22","lon":"07°51'Pis","deg":337.85,"R":false,"speed":0.09},
    {"dt":"2024-01-29","lon":"09°12'Pis","deg":339.20,"R":false,"speed":0.08},
    {"dt":"2024-02-05","lon":"10°24'Pis","deg":340.40,"R":false,"speed":0.08},
    {"dt":"2024-02-12","lon":"11°26'Pis","deg":341.43,"R":false,"speed":0.07},
    {"dt":"2024-02-19","lon":"12°17'Pis","deg":342.28,"R":false,"speed":0.07},
    {"dt":"2024-02-26","lon":"12°56'Pis","deg":342.93,"R":false,"speed":0.06}
  ]
}
```

---

### Tool 13: `find_aspect_exact_dates`

**Описание:** Поиск точных дат формирования и расхождения конкретного аспекта между двумя планетами (или планетой и точкой карты) в заданный период.

#### Input Schema

```json
{
  "type": "object",
  "required": ["planet1", "planet2", "aspect", "date_from", "date_to"],
  "properties": {
    "planet1": {"type": "string", "description": "Транзитная планета (код)"},
    "planet2": {
      "type": "string",
      "description": "Вторая планета/точка. Если это натальная точка — передать natal_data"
    },
    "natal_data": {
      "$ref": "#/definitions/BirthData",
      "description": "Обязательно, если planet2 — натальная точка"
    },
    "aspect": {
      "type": "string",
      "enum": ["Cnj","Opp","Tri","Squ","Sex","Qui","BiQ","SSx","SSq","Ses"],
      "description": "Тип аспекта"
    },
    "date_from": {"type": "string", "format": "date"},
    "date_to": {"type": "string", "format": "date"},
    "orb": {"type": "number", "default": 1.0, "description": "Орбис в градусах для определения начала/конца"}
  }
}
```

#### Output Schema & Пример

```json
{
  "planet1":"Sa",
  "planet2":"Su",
  "aspect":"Cnj",
  "orb_used":1.0,
  "occurrences":[
    {
      "approach_date":"2024-02-15",
      "exact_date":"2024-04-01",
      "separation_date":"2024-05-20",
      "retrograde_exact":null,
      "direct_exact":"2024-04-01",
      "is_triple_pass":false,
      "peak_orb":0.02
    }
  ]
}
```

---

### Tool 14: `calculate_antiscia`

**Описание:** Антисции (отражения по оси Рак/Козерог, 0° Cancer — 0° Capricorn) и контрантисции (отражения по оси Овен/Весы) для планет натальной карты.

#### Input Schema

```json
{
  "type": "object",
  "required": ["natal"],
  "properties": {
    "natal": {
      "oneOf": [{"$ref": "#/definitions/NatalChartFull"}, {"$ref": "#/definitions/BirthData"}]
    },
    "include_transits_date": {
      "type": "string",
      "format": "date",
      "description": "Если задано — найти аспекты транзитных планет к антисциям"
    }
  }
}
```

#### Output Schema & Пример

```json
{
  "antiscia":{
    "Su":{"natal_lon":"24°45'Pis","antiscia":"05°15'Lib","contraantiscia":"05°15'Ari"},
    "Mo":{"natal_lon":"18°32'Sag","antiscia":"11°27'Cap","contraantiscia":"11°27'Can"},
    "Ve":{"natal_lon":"16°22'Tau","antiscia":"13°38'Leo","contraantiscia":"13°38'Aqu"},
    "Asc":{"natal_lon":"00°12'Can","antiscia":"29°48'Gem","contraantiscia":"29°48'Sag"}
  },
  "mutual_antiscia_aspects":[
    {"p1":"Su","p2":"Mo","type":"antiscia_cnj","orb":2.33}
  ],
  "transit_antiscia_aspects":null
}
```

---

## 4. Technical Architecture

### Обзор архитектуры

```
┌─────────────────────────────────────────────────┐
│              MCP Client (Claude Desktop)         │
│           (stdio transport — JSON-RPC 2.0)       │
└─────────────────┬───────────────────────────────┘
                  │ stdin/stdout
┌─────────────────▼───────────────────────────────┐
│                  server.py                       │
│         (MCP SDK: @mcp.tool decorators)          │
│    Tool dispatch → tools/*.py modules            │
└──────────┬──────────────┬───────────────────────┘
           │              │
┌──────────▼──────┐  ┌───▼──────────────────────┐
│  core/           │  │  core/                   │
│  ephemeris_      │  │  geocoding.py            │
│  provider.py     │  │  (geopy + timezonefinder)│
│  (pyswisseph)    │  └──────────────────────────┘
└──────────┬───────┘
           │
┌──────────▼───────┐    ┌──────────────────────┐
│  ephe/           │    │  core/formatters.py   │
│  *.se1 files     │    │  (LLM output format)  │
│  (ephemeris data)│    └──────────────────────┘
└──────────────────┘
```

### Структура проекта

```
astro-mcp/
├── src/
│   └── astro_mcp/
│       ├── __init__.py        # package marker + version
│       ├── __main__.py        # python -m astro_mcp entry point
│       ├── server.py          # MCP server: tool registration, error handling
│       ├── config.py          # Settings (via pydantic-settings + env vars)
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── natal.py            # calculate_natal_chart
│       │   ├── transits.py         # calculate_transits
│       │   ├── progressions.py     # calculate_secondary_progressions
│       │   ├── returns.py          # calculate_solar_return + calculate_lunar_return
│       │   ├── synastry.py         # calculate_synastry + calculate_composite_chart
│       │   ├── rectification.py    # calculate_rectification_hints
│       │   ├── profections.py      # calculate_profections
│       │   ├── arabic_parts.py     # calculate_arabic_parts
│       │   ├── ephemeris.py        # get_ephemeris + find_aspect_exact_dates
│       │   ├── planetary_hours.py  # get_planetary_hours
│       │   └── antiscia.py         # calculate_antiscia
│       └── core/
│           ├── __init__.py
│           ├── ephemeris_provider.py  # Swiss Ephemeris wrapper (pyswisseph)
│           ├── geocoding.py           # город → (lat, lon, tz)
│           └── formatters.py          # LLM-optimized serialization
├── ephe/                          # Swiss Ephemeris data files (.se1)
├── tests/
│   ├── conftest.py
│   ├── reference_data/            # known-good астрологические данные
│   ├── test_natal.py
│   ├── test_transits.py
│   ├── test_progressions.py
│   ├── test_returns.py
│   ├── test_synastry.py
│   ├── test_rectification.py
│   ├── test_arabic_parts.py
│   └── test_formatters.py
├── pyproject.toml
├── README.md
└── PRD.md
```

### Компоненты модуля `core`

#### `ephemeris_provider.py`

Обёртка над `pyswisseph`. Централизует:
- Инициализацию пути к файлам эфемерид (`swe.set_ephe_path`)
- Расчёт Юлианского дня (`swe.julday`)
- Расчёт позиций планет (`swe.calc_ut`)
- Расчёт домов и углов (`swe.houses`)
- Определение ретроградности по знаку скорости
- Расчёт восхода/захода Солнца (`swe.rise_trans`)
- Точный поиск аспектов методом бисекции

#### `geocoding.py`

- Геокодирование строки города через `geopy` (Nominatim → OpenCage fallback)
- Определение часового пояса по координатам через `timezonefinder`
- Конвертация локального времени в UTC через `zoneinfo` / `pytz`
- Кэширование результатов геокодирования (LRU cache)

#### `formatters.py`

- Конвертация градусов (десятичные ↔ DMS)
- Сериализация `ChartPoint` в компактный словарь
- Фильтрация аспектов по минимальному орбису
- Сортировка аспектов по орбису (ascending)
- Финальный `json.dumps` без пробелов

---

## 5. Data Models

### Базовые типы (Python dataclasses / TypedDict)

```python
# BirthData — входные данные рождения
class BirthData(TypedDict):
    date: str          # "YYYY-MM-DD"
    time: str          # "HH:MM" или "HH:MM:SS"
    location: str | CoordDict   # город или {"lat": float, "lon": float, "tz": str}

# Resolved coordinates (internal)
@dataclass
class GeoLocation:
    lat: float
    lon: float
    tz: str            # IANA timezone
    name: str          # название для метаданных

# ChartPoint — планета или угол в карте
@dataclass
class ChartPoint:
    lon_decimal: float    # долгота в десятичных градусах [0, 360)
    sign: str             # "Ari" | "Tau" | ... | "Pis"
    sign_lon: float       # долгота внутри знака [0, 30)
    house: int | None     # номер дома [1-12] или None для углов
    retrograde: bool
    speed: float          # суточная скорость в градусах
    
    def dms(self) -> str:
        """Возвращает "DD°MM'SS\""."""

# Aspect — аспект между двумя точками
@dataclass
class Aspect:
    point1: str          # код планеты/угла
    point2: str          # код планеты/угла
    aspect_type: str     # "Cnj" | "Opp" | "Tri" | "Squ" | "Sex" | ...
    orb: float           # орбис в градусах (всегда положительный)
    applying: bool       # True = применяющийся, False = уходящий
    exact_date: str | None  # дата точного аспекта (ISO8601)

# HouseCusp — куспид дома
@dataclass
class HouseCusp:
    number: int           # 1-12
    lon_decimal: float    # долгота куспида
    sign: str             # знак куспида
    ruler: str            # классический управитель
    modern_ruler: str | None
```

### Коды планет и объектов

| Код | Тело | Swiss Ephemeris ID |
|---|---|---|
| `Su` | Солнце | `swe.SUN` (0) |
| `Mo` | Луна | `swe.MOON` (1) |
| `Me` | Меркурий | `swe.MERCURY` (2) |
| `Ve` | Венера | `swe.VENUS` (3) |
| `Ma` | Марс | `swe.MARS` (4) |
| `Ju` | Юпитер | `swe.JUPITER` (5) |
| `Sa` | Сатурн | `swe.SATURN` (6) |
| `Ur` | Уран | `swe.URANUS` (7) |
| `Ne` | Нептун | `swe.NEPTUNE` (8) |
| `Pl` | Плутон | `swe.PLUTO` (9) |
| `Ch` | Хирон | `swe.CHIRON` (15) |
| `Ce` | Церера | `swe.CERES` (17) |
| `Pa` | Паллада | `swe.PALLAS` (18) |
| `Ju2` | Юнона | `swe.JUNO` (19) |
| `Ve2` | Веста | `swe.VESTA` (20) |
| `NN` | Северный узел | `swe.TRUE_NODE` (11) |
| `SN` | Южный узел | вычисляется как `NN + 180°` |

### Коды аспектов и орбисы по умолчанию

| Код | Аспект | Угол | Орбис (планета-планета) | Орбис (угол) |
|---|---|---|---|---|
| `Cnj` | Соединение | 0° | 8° | 10° |
| `Opp` | Оппозиция | 180° | 8° | 10° |
| `Tri` | Трин | 120° | 7° | 8° |
| `Squ` | Квадратура | 90° | 7° | 8° |
| `Sex` | Секстиль | 60° | 5° | 6° |
| `Qui` | Квинтиль | 72° | 2° | — |
| `BiQ` | Биквинтиль | 144° | 2° | — |
| `SSx` | Полусекстиль | 30° | 2° | — |
| `SSq` | Полуквадрат | 45° | 2° | — |
| `Ses` | Sesquiquadrate | 135° | 2° | — |

### Управители знаков

```python
RULERS = {
    "Ari": ("Ma", None),   # (классический, современный)
    "Tau": ("Ve", None),
    "Gem": ("Me", None),
    "Can": ("Mo", None),
    "Leo": ("Su", None),
    "Vir": ("Me", None),
    "Lib": ("Ve", None),
    "Sco": ("Ma", "Pl"),
    "Sag": ("Ju", None),
    "Cap": ("Sa", None),
    "Aqu": ("Sa", "Ur"),
    "Pis": ("Ju", "Ne"),
}
```

---

## 6. LLM Output Optimization

### Принципы минимизации токенов

Вывод инструментов MCP напрямую попадает в контекст LLM. Каждый сохранённый токен — это экономия стоимости и увеличение доступного пространства для рассуждений агента.

#### Стратегии

1. **Кодирование вместо полных названий**
   - `"Saturn"` → `"Sa"` (−5 токенов)
   - `"Capricorn"` → `"Cap"` (−4 токена)
   - `"Conjunction"` → `"Cnj"` (−5 токенов)

2. **Нет JSON-prettify**
   ```python
   json.dumps(data, separators=(',', ':'), ensure_ascii=False)
   ```
   Экономия ~15% от объёма средней карты.

3. **Плоская структура вместо глубокой вложенности**
   ```json
   // Плохо:
   {"planet": {"name": "Sun", "position": {"sign": "Pisces", "degree": 24}}}
   // Хорошо:
   {"Su":{"sign":"Pis","deg":24.75}}
   ```

4. **Числа с точностью 2 знака**
   ```python
   round(decimal_degrees, 2)  # 24.7512... → 24.75
   ```

5. **Булевы значения только когда `true`**
   Поле `"R"` (ретроградность) включается как `"R":true`, при прямом движении — опускается.

6. **Аспекты отсортированы по орбису**
   Самые тесные — первыми: LLM сразу видит наиболее значимые.

7. **Опциональные поля исключаются если `null`**
   ```python
   {k: v for k, v in data.items() if v is not None}
   ```

8. **Пример разницы объёма**
   | Формат | Объём для полной натальной карты | Токены (approx) |
   |---|---|---|
   | Verbose JSON | ~8 КБ | ~2000 |
   | Compact (наш) | ~2 КБ | ~500 |
   | Экономия | ~75% | ~1500 токенов |

9. **Параметр `degree_format`**
   - `"dms"` — `"24°45'12\""` — предпочтителен для астролога
   - `"dec"` — `24.75` — короче, предпочтителен когда нужен чистый JSON для LLM

---

## 7. Rectification Algorithm

### Описание алгоритма ректификации

Ректификация — процесс уточнения времени рождения на основе анализа значимых жизненных событий. Алгоритм реализует статистическое ранжирование вариантов времени.

### Шаг 1: Генерация кандидатов

```
time_range = [time_from ... time_to] с шагом time_step_min
Для шага 4 минуты и диапазона 2 часа → 30 кандидатов
(4 минуты ≈ 1° смещение Асцендента)
```

### Шаг 2: Маппинг типов событий на астрологические сигнификаторы

```python
EVENT_SIGNIFICATORS = {
    "marriage":        [("Ve",["7th_cusp","DSC","Ju"]),  ("7th_lord", ["Cnj","Squ","Opp","Tri"])],
    "divorce":         [("Sa",["Ve","7th_cusp","DSC"]),   ("Ma",["Ve","7th_cusp"])],
    "birth_child":     [("Ju",["5th_cusp","5th_lord"]),   ("Mo",["5th_cusp","Su"])],
    "death_close":     [("Sa",["4th_cusp","8th_cusp"]),   ("Pl",["Mo","Su","4th_lord"])],
    "career_rise":     [("Ju",["MC","Su","10th_lord"]),   ("Su",["MC","10th_cusp"])],
    "career_fall":     [("Sa",["MC","Su"]),                ("Pl",["MC","10th_cusp"])],
    "relocation":      [("Ur",["4th_cusp","IC"]),          ("Sa",["4th_cusp"])],
    "accident":        [("Ma",["ASC","1st_lord","Mo"]),   ("Ur",["ASC","Ma"])],
    "illness_major":   [("Sa",["ASC","Mo","Su"]),          ("Ne",["ASC","6th_cusp"])],
    "surgery":         [("Ma",["ASC","6th_cusp","8th"]),  ("Pl",["ASC","Mo"])],
    "financial_gain":  [("Ju",["2nd_cusp","Ve","FortPt"])],
    "financial_loss":  [("Sa",["2nd_cusp","Ve"]),          ("Ne",["2nd_cusp","Ju"])],
}
```

### Шаг 3: Расчёт индикаторов для каждого события × каждого кандидата

Для каждого кандидата (времени рождения):
1. Строится натальная карта
2. Для каждого события и каждой применимой техники:
   - **Транзиты:** рассчитать планетарные позиции на дату события, найти аспекты к натальным точкам-сигнификаторам
   - **Прогрессии:** рассчитать вторичные прогрессии на дату события, найти аспекты прогрессированных точек к натальным
   - **Профекции:** определить профицированный дом и управителя, проверить активацию нужных домов

### Шаг 4: Скоринг

```python
def score_event_match(orb: float, aspect_type: str, technique: str) -> float:
    """
    Базовый балл аспекта.
    """
    base_scores = {
        "Cnj": 10.0, "Opp": 9.0, "Squ": 8.5, "Tri": 7.0,
        "Sex": 5.0, "SSq": 3.0, "Ses": 3.0, "SSx": 2.0
    }
    technique_weights = {
        "transits": 1.0,
        "progressions": 1.2,   # прогрессии к углам — надёжнее
        "profections": 0.8
    }
    
    base = base_scores.get(aspect_type, 2.0)
    orb_factor = max(0, 1 - orb / MAX_ORB)  # линейное затухание
    technique_weight = technique_weights[technique]
    
    return base * orb_factor * technique_weight

def score_candidate(candidate_time: str, events: list[Event]) -> float:
    """
    Итоговый скор кандидата = сумма скоров по всем событиям.
    Нормализован к [0, 100].
    """
    total = sum(
        max(score_event_match(ind.orb, ind.asp, technique) for ind in indicators)
        for event, technique, indicators in matched_indicators
    )
    return normalize(total, max_possible_score)
```

### Шаг 5: Ранжирование и фильтрация

- Кандидаты ранжируются по `score` (убывание)
- Возвращается `top_n` кандидатов (default: 5)
- Уровень уверенности (`confidence`):
  - `"high"`: ≥ 5 событий, лучший кандидат отрыв > 15 баллов от второго
  - `"medium"`: 3-4 события ИЛИ отрыв 8-15 баллов
  - `"low"`: < 3 событий ИЛИ отрыв < 8 баллов

### Шаг 6: Специальные проверки

1. **Смещение ASC:** если у первого кандидата ASC в начале знака (< 3° или > 27°) — предупреждение, что смещение на несколько минут может изменить знак ASC
2. **Дублирующиеся ASC:** если два кандидата имеют одинаковый знак ASC — объединить в диапазон
3. **Пустой результат:** если score < 30 для всех → вернуть `NO_CANDIDATES` с рекомендацией добавить события

---

## 8. Non-Functional Requirements

### Производительность

| Инструмент | Max latency (p95) | Примечание |
|---|---|---|
| `calculate_natal_chart` | 300 ms | Сингл-карта с аспектами |
| `calculate_transits` (1 дата) | 200 ms | |
| `calculate_transits` (30 дней) | 500 ms | |
| `calculate_secondary_progressions` | 400 ms | |
| `calculate_solar_return` | 500 ms | Бисекция для точного момента |
| `calculate_lunar_return` | 600 ms | Бисекция, Луна быстрее |
| `calculate_synastry` | 600 ms | Две карты + межаспекты |
| `calculate_composite_chart` | 700 ms | |
| `calculate_rectification_hints` | 5–30 s | Зависит от диапазона и числа событий |
| `get_ephemeris` (365 дней) | 1 s | |
| `get_planetary_hours` | 300 ms | |
| Геокодирование (кэш промах) | 2 s | Сетевой запрос |
| Геокодирование (кэш попадание) | < 5 ms | LRU cache |

### Точность расчётов

- Swiss Ephemeris обеспечивает точность < 1" дуги (достаточно для профессиональной астрологии)
- Минимальный временной шаг бисекции при поиске точных дат: 1 секунда
- Геокодирование: точность до 0.001° (~ 100 м — достаточно для всех астрологических техник)
- Часовой пояс: использовать историческую базу `tzdata` (учитывает переходы на летнее время и изменения зон)

### Обработка ошибок

- Все ошибки возвращаются как JSON с полями `error`, `code`, `message`
- Никогда не бросать исключения Python напрямую в MCP-ответ
- Логировать ошибки Swiss Ephemeris в stderr (не в stdout — занят stdio-транспортом)

```python
# Стандартный формат ошибки
{
  "error": true,
  "code": "GEOCODE_FAILED",
  "message": "City 'Nsk' not found. Please provide full city name or coordinates.",
  "hint": "Try: 'Novosibirsk, Russia' or provide lat/lon directly"
}
```

### Безопасность и изоляция

- Сервер не использует сеть во время расчётов (только при геокодировании)
- Геокодирование можно отключить, передавая координаты напрямую
- Нет хранения пользовательских данных между вызовами (stateless)
- Файлы эфемерид читаются только для чтения

---

## 9. Dependencies & Installation

### Зависимости

```toml
# pyproject.toml
[project]
name = "astro-mcp"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",              # Official MCP Python SDK (Anthropic)
    "pyswisseph>=2.10.3.2",    # Swiss Ephemeris Python bindings
    "geopy>=2.4.0",            # Geocoding (Nominatim, OpenCage, etc.)
    "timezonefinder>=6.5.0",   # Timezone lookup by coordinates (offline)
    "pydantic>=2.5.0",         # Input validation
    "pydantic-settings>=2.1.0",# Config via env vars
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.25.0",
]

[project.scripts]
astro-mcp = "astro_mcp.__main__:main"
```

### Скачивание файлов эфемерид Swiss Ephemeris

Swiss Ephemeris требует локальных файлов данных в формате `.se1`. Без них точность падает до JPL Moshier (менее точной аппроксимации).

#### Необходимые файлы

| Файл | Что содержит | Размер |
|---|---|---|
| `seas_18.se1` | Астероиды 1800-2400 | ~3 МБ |
| `sepl_18.se1` | Планеты 1800-2400 | ~6 МБ |
| `semo_18.se1` | Луна 1800-2400 | ~3 МБ |
| `fixstars.cat` | Фиксированные звёзды | ~1 МБ |

Для расширенного диапазона дат добавьте файлы других эпох (`seas_06.se1`, `sepl_06.se1` и т.д.).

#### Скрипт установки

```bash
# 1. Клонировать репозиторий
git clone https://github.com/your-org/astro-mcp
cd astro-mcp

# 2. Создать виртуальное окружение
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Установить зависимости
pip install -e ".[dev]"

# 4. Создать папку для эфемерид
mkdir -p ephe

# 5. Скачать файлы эфемерид (официальный FTP Astrodienst)
cd ephe
wget "https://www.astro.com/ftp/swisseph/ephe/seas_18.se1"
wget "https://www.astro.com/ftp/swisseph/ephe/sepl_18.se1"
wget "https://www.astro.com/ftp/swisseph/ephe/semo_18.se1"
# Для дат до 1800 или после 2400:
# wget "https://www.astro.com/ftp/swisseph/ephe/sepl_06.se1"
# wget "https://www.astro.com/ftp/swisseph/ephe/semo_06.se1"
cd ..

# 6. Установить переменную окружения
export EPHE_PATH="$(pwd)/ephe"

# 7. Запустить тесты
pytest tests/
```

### Конфигурация для Claude Desktop

```json
{
  "mcpServers": {
    "astro": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "astro_mcp"],
      "env": {
        "EPHE_PATH": "/path/to/astro-mcp/ephe",
        "GEOCODING_PROVIDER": "nominatim",
        "GEOCODING_USER_AGENT": "astro-mcp/1.0",
        "LOG_LEVEL": "WARNING"
      }
    }
  }
}
```

### Переменные окружения

| Переменная | Default | Описание |
|---|---|---|
| `EPHE_PATH` | `./ephe` | Путь к файлам Swiss Ephemeris |
| `GEOCODING_PROVIDER` | `nominatim` | Провайдер геокодирования: `nominatim`, `opencage` |
| `OPENCAGE_API_KEY` | — | API ключ OpenCage (если `GEOCODING_PROVIDER=opencage`) |
| `GEOCODING_USER_AGENT` | `astro-mcp/1.0` | User-Agent для запросов к Nominatim |
| `GEOCODE_CACHE_SIZE` | `512` | Размер LRU кэша геокодирования |
| `DEFAULT_HOUSE_SYSTEM` | `P` | Система домов по умолчанию |
| `DEFAULT_ORB_FACTOR` | `1.0` | Множитель орбисов (0.5–1.5) |
| `LOG_LEVEL` | `WARNING` | Уровень логирования (DEBUG/INFO/WARNING/ERROR) |

---

## 10. Testing Strategy

### Принципы тестирования

Астрологические расчёты верифицируются сравнением с эталонными данными из профессиональных программ (Solar Fire, Astro.com, Astrodienst).

### Типы тестов

#### 1. Unit тесты — разреженные вычисления

```python
# tests/test_natal.py — пример
def test_known_natal_chart():
    """
    Данные рождения: Albert Einstein
    14 марта 1879, 11:30 LMT, Ulm, Germany
    Эталон: Astro.com chart
    """
    result = calculate_natal_chart(
        date="1879-03-14",
        time="11:30",
        location={"lat": 48.4011, "lon": 9.9876, "tz": "Europe/Berlin"}
    )
    
    assert result["planets"]["Su"]["sign"] == "Pis"
    assert abs(result["planets"]["Su"]["deg"] - 23.50) < 0.02  # 23°29'
    assert result["planets"]["Mo"]["sign"] == "Sag"
    assert result["angles"]["Asc"]["sign"] == "Can"
    assert result["angles"]["MC"]["sign"] == "Pis"
```

#### 2. Тесты аспектов

```python
def test_aspect_orb_calculation():
    """Проверка точности вычисления орбисов."""
    # Соединение с орбисом 2°
    asp = calculate_aspect("Su", 24.75, "Ju", 26.50)
    assert asp.aspect_type == "Cnj"
    assert abs(asp.orb - 1.75) < 0.01

def test_applying_vs_separating():
    """Применяющийся vs уходящий аспект."""
    # Su скорость +1°/день, Ju скорость +0.1°/день
    # Su догоняет Ju → применяющийся
    ...
```

#### 3. Тесты геокодирования

```python
def test_geocode_known_cities():
    known = [
        ("Moscow, Russia", 55.75, 37.62, "Europe/Moscow"),
        ("New York, USA", 40.71, -74.01, "America/New_York"),
        ("Tokyo, Japan", 35.68, 139.69, "Asia/Tokyo"),
    ]
    for city, expected_lat, expected_lon, expected_tz in known:
        result = geocode(city)
        assert abs(result.lat - expected_lat) < 0.1
        assert result.tz == expected_tz
```

#### 4. Тесты точных дат аспектов

```python
def test_saturn_sun_conjunction_2024():
    """
    Сатурн-Солнце соединение 2024 — проверка по астрологическому календарю.
    """
    result = find_aspect_exact_dates(
        planet1="Sa", planet2="Su", aspect="Cnj",
        date_from="2024-01-01", date_to="2024-12-31"
    )
    # По данным астрологического альманаха: Sa-Su Cnj ~ 1 апреля 2024
    assert len(result["occurrences"]) >= 1
    assert "2024-04" in result["occurrences"][0]["exact_date"]
```

#### 5. Тесты ректификации

```python
def test_rectification_known_person():
    """
    Ректификация известного человека с подтверждённым временем рождения.
    Намеренно скрываем точное время и проверяем, что алгоритм его находит.
    """
    # Берём известную дату и список событий
    # Передаём диапазон ±1 час от реального времени
    # Проверяем, что реальное время в top-3
    ...
```

#### 6. Тесты форматирования

```python
def test_compact_json_output():
    """Нет лишних пробелов в выводе."""
    output = format_natal_chart(mock_chart)
    assert " " not in json.dumps(output)  # no spaces

def test_dms_format():
    assert decimal_to_dms(24.7534) == "24°45'12\""
    assert decimal_to_dms(0.0028) == "00°00'10\""
```

### Эталонные данные

Папка `tests/reference_data/` содержит JSON-файлы с эталонными натальными картами:
- `einstein_1879.json` — Альберт Эйнштейн
- `lennon_1940.json` — Джон Леннон
- `test_summer_solstice.json` — точки солнцестояний (верифицируемые математически)

### CI/CD

```yaml
# .github/workflows/test.yml
- Запуск pytest на Python 3.11 и 3.12
- Проверка, что файлы эфемерид загружены (условие: EPHE_PATH)
- Coverage > 80%
- Linting: ruff, mypy
```

---

## 11. Future Enhancements

### v1.1 — Дополнительные техники

- **`calculate_solar_arc`** — Солнечная дуга (SA = прогрессированное Солнце - натальное Солнце, прибавить к каждой планете)
- **`calculate_tertiary_progressions`** — Третичные прогрессии (день = лунный месяц)
- **`calculate_firdaria`** — Фирдариат (шиитская планетарная периодизация)
- **`calculate_decennials`** — Деканальные периоды (Vettius Valens)

### v1.2 — Элективная астрология

- **`find_election_windows`** — Поиск благоприятных временных окон для важных действий (заключение договора, начало проекта, операция)
- Параметры: тип деятельности, диапазон поиска, запрещённые конфигурации (Лунное затмение, void-of-course Moon)

### v1.3 — Фиксированные звёзды и эклиптика

- **`get_fixed_stars`** — Позиции и паролльные фиксированные звёзды (Regulus, Spica, Algol и др.)
- Аспекты планет к фиксированным звёздам (с орбисом 1°)

### v2.0 — Ведическая астрология (Jyotish)

- Сидерический зодиак (Lahiri Ayanamsha)
- Система домов Whole Sign (основная для Jyotish)
- Накшатры (27 лунных стоянок)
- Даша системы (Vimshottari — основная)
- Навамша (D9) и другие варги

### v2.1 — Хранилище и персонализация

- Локальная SQLite база для хранения натальных карт пользователей
- **`save_chart`** / **`load_chart`** — сохранение и загрузка карт по имени
- История транзитных прогнозов для сравнения с событиями

### v2.2 — Интерактивные ресурсы MCP

- **MCP Resources:** предоставлять статический контент (интерпретационные тексты, планетарные ключевые слова)
- **MCP Prompts:** предустановленные промпты для агента (шаблоны консультации, структура интерпретации)

### v2.3 — Производительность

- Кэширование рассчитанных карт в памяти (LRU с TTL)
- Предрасчёт эфемерид на запрашиваемый диапазон в отдельном потоке
- Опциональная поддержка HTTP+SSE транспорта для web-интеграции

---

## Appendix A: Ссылки

- [Swiss Ephemeris Documentation](https://www.astro.com/swisseph/swephprg.htm)
- [pyswisseph PyPI](https://pypi.org/project/pyswisseph/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Model Context Protocol Specification](https://modelcontextprotocol.io)
- [Placidus House System](https://en.wikipedia.org/wiki/Domification#Placidus)
- [Secondary Progressions](https://www.skyscript.co.uk/sec_progression.html)

## Appendix B: Глоссарий

| Термин | Определение |
|---|---|
| **MCP** | Model Context Protocol — протокол интеграции инструментов для LLM |
| **Swiss Ephemeris** | Высокоточная астрономическая база данных от Astrodienst |
| **Natal chart** | Натальная карта — снимок неба в момент рождения |
| **Transit** | Транзит — текущее положение планеты относительно натальной карты |
| **Progression** | Прогрессия — символическое продвижение планет вперёд |
| **Solar Return** | Солнечное возвращение (соляр) — ежегодная карта нового цикла |
| **Lunar Return** | Лунное возвращение (лунар) — ежемесячная карта нового лунного цикла |
| **Synastry** | Синастрия — сравнение двух натальных карт |
| **Composite Chart** | Составная карта — символическая карта пары |
| **Profections** | Профекции — эллинистическая техника годовых периодов |
| **Rectification** | Ректификация — уточнение времени рождения |
| **Arabic Parts / Lots** | Арабские части — чувствительные точки по формулам |
| **Antiscia** | Антисции — отражения по оси солнцестояний |
| **Placidus** | Система домов, основанная на разделении полудуг |
| **Whole Sign** | Система домов: каждый дом = один знак зодиака |
| **Orb** | Орбис — допустимое отклонение от точного аспекта |
| **JD / Julian Day** | Юлианский день — непрерывный счёт дней для астрономических расчётов |
