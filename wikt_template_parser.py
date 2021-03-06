import copy
import re

import wikitextparser as wtp
from bs4 import BeautifulSoup

from itertools import product

split_regex = r'\n| |<br\/>|<br \/>'

def table_to_2d(table_tag):
    rowspans = []  # track pending rowspans
    rows = table_tag.find_all('tr')

    # first scan, see how many columns we need
    colcount = 0
    for r, row in enumerate(rows):
        cells = row.find_all(['td', 'th'], recursive=False)
        # count columns (including spanned).
        # add active rowspans from preceding rows
        # we *ignore* the colspan value on the last cell, to prevent
        # creating 'phantom' columns with no actual cells, only extended
        # colspans. This is achieved by hardcoding the last cell width as 1.
        # a colspan of 0 means “fill until the end” but can really only apply
        # to the last cell; ignore it elsewhere.
        colcount = max(
            colcount,
            sum(int(c.get('colspan', 1)) or 1 for c in cells[:-1]) + len(cells[-1:]) + len(rowspans))
        # update rowspan bookkeeping; 0 is a span to the bottom.
        rowspans += [int(c.get('rowspan', 1)) or len(rows) - r for c in cells]
        rowspans = [s - 1 for s in rowspans if s > 1]

    # it doesn't matter if there are still rowspan numbers 'active'; no extra
    # rows to show in the table means the larger than 1 rowspan numbers in the
    # last table row are ignored.

    # build an empty matrix for all possible cells
    table = [[None] * colcount for row in rows]

    # fill matrix from row data
    rowspans = {}  # track pending rowspans, column number mapping to count
    for row, row_elem in enumerate(rows):
        span_offset = 0  # how many columns are skipped due to row and colspans
        for col, cell in enumerate(row_elem.find_all(['td', 'th'], recursive=False)):
            # adjust for preceding row and colspans
            col += span_offset
            while rowspans.get(col, 0):
                span_offset += 1
                col += 1

            # fill table data
            rowspan = rowspans[col] = int(cell.get('rowspan', 1)) or len(rows) - row
            colspan = int(cell.get('colspan', 1)) or colcount - col
            # next column is offset by the colspan
            span_offset += colspan - 1
            value = cell.get_text()
            for drow, dcol in product(range(rowspan), range(colspan)):
                try:
                    table[row + drow][col + dcol] = value
                    rowspans[col + dcol] = rowspan
                except IndexError:
                    # rowspan or colspan outside the confines of the table
                    pass

        # update rowspan bookkeeping
        rowspans = {c: s - 1 for c, s in rowspans.items() if s > 1}

    return table

r_case_opencorpora = {
    'и': 'nomn',
    'р': 'gent',
    'д': 'datv',
    'в': 'accs',
    'т': 'ablt',
    'п': 'loct',
    'им.': 'nomn',
    'род.': 'gent',
    'дат.': 'datv',
    'вин.': 'accs',
    'твор.': 'ablt',
    'пр.': 'loct',
    'именительный': 'nomn',
    'родительный': 'gent',
    'дательный': 'datv',
    'винительный': 'accs',
    'творительный': 'ablt',
    'предложный': 'loct',
    'именительного': 'nomn',
    'родительного': 'gent',
    'дательного': 'datv',
    'винительного': 'accs',
    'творительного': 'ablt',
    'предложного': 'loct',
}
r_case_universalD = {
    'и': 'Nom',
    'р': 'Gen',
    'д': 'Dat',
    'в': 'Acc',
    'т': 'Ins',
    'п': 'Loc',
    'им.': 'Nom',
    'род.': 'Gen',
    'дат.': 'Dat',
    'вин.': 'Acc',
    'твор.': 'Ins',
    'пр.': 'Loc',
    'именительный': 'Nom',
    'родительный': 'Gen',
    'дательный': 'Dat',
    'винительный': 'Acc',
    'творительный': 'Ins',
    'предложный': 'Loc',
    'именительного': 'Nom',
    'родительного': 'Gen',
    'дательного': 'Dat',
    'винительного': 'Acc',
    'творительного': 'Ins',
    'предложного': 'Loc',
}
r_number = {
    'ед': 'Sing',
    '1': 'Sing',
    'мн': 'Plur',
}
r_tense_opencorpora = {
    'наст': 'pres',
    'пр': 'past',
    'буд': 'futr',
}
r_tense_universalD = {
    'наст': 'Pres',
    'пр': 'Past',
    'буд': 'Fut',
}
r_gender = {
    'м': 'Masc',
    'ж': 'Fem',
    'с': 'Neut',
    'm': 'Masc',
    'f': 'Fem',
    'n': 'Neut',
}
r_person_opencorpora = {
    '1': '1per',
    '2': '2per',
    '3': '3per',
    'я': '1per',
    'ты': '2per',
    'он': '3per',
    'мы': '1per',
    'вы': '2per',
    'они': '3per',
}
r_person_universalD = {
    '1': '1',
    '2': '2',
    '3': '3',
    'я': '1',
    'ты': '2',
    'он': '3',
    'мы': '1',
    'вы': '2',
    'они': '3',
}
r_anim = {
    'a': 'Anim',
    'ina': 'Inan',
    'одушевлённый': 'Anim',
    'неодушевлённый': 'Inan',
}
r_degree_opencorpora = {
    'качественное': 'Qual',
}
r_degree_univarsalD = {
    'качественное': 'Pos',
}

known_templates = ['Форма-сущ', 'Форма-гл', 'conj ru', 'сущ-ru']
advansed_templates = ['сущ ru', 'прил ru', 'Фам ru', 'гл ru']

def known_template(template):
    template_name = template.name.strip()
    if template_name in known_templates:
        return True

    for i in advansed_templates:
        if i in template_name:
            return True
    return False

def get_name_value(argument):
    name = argument.name.strip()
    value = argument.value.strip()
    return name, value if len(value) > 0 else None

def parse_template(word_acc, template):
    from wiktparser import search_section_for_template, get_word_from_slogi, get_wikitext_api_expandtemplates

    variants = []
    template_name = template.name.strip()

    opencorpora_tag = {'tag': {}}
    universalD_tag = {'tag': {}}

    if template_name == 'Форма-сущ':
        opencorpora_tag['pos'] = 'NOUN'
        universalD_tag['pos'] = 'NOUN'

        for argument in template.arguments:
            name, value = get_name_value(argument)

            if name in ['база', '1'] and value is not None:
                opencorpora_tag['base'] = value
                universalD_tag['base'] = value
                continue

            if name in ['падеж', '2'] and value is not None:
                if value in ['ив', 'рв', 'рдп']:
                    opencorpora_tag['tag']['Case'] = []
                    universalD_tag['tag']['Case'] = []
                    for v in value:
                        opencorpora_tag['tag']['Case'].append(r_case_opencorpora.get(v))
                        universalD_tag['tag']['Case'].append(r_case_universalD.get(v))
                    continue

                if ' и ' in value:
                    opencorpora_tag['tag']['Case'] = []
                    universalD_tag['tag']['Case'] = []
                    for v in value.split(' и '):
                        opencorpora_tag['tag']['Case'].append(r_case_opencorpora.get(v))
                        universalD_tag['tag']['Case'].append(r_case_universalD.get(v))
                    continue

                opencorpora_tag['tag']['Case'] = r_case_opencorpora.get(value)
                universalD_tag['tag']['Case'] = r_case_universalD.get(value)
                continue

            if name in ['число', '3'] and value is not None:
                opencorpora_tag['tag']['Number'] = r_number[value]
                universalD_tag['tag']['Number'] = r_number[value]
                continue

            if name in ['помета', '5']:
                continue

            if name == 'число' and value is not None:
                opencorpora_tag['tag']['Number'] = r_number[value]
                universalD_tag['tag']['Number'] = r_number[value]
                continue

            if name == 'слоги':
                continue

        return [[word_acc, opencorpora_tag, universalD_tag]]

    if template_name == 'Форма-гл':
        opencorpora_tag['pos'] = 'VERB'
        universalD_tag['pos'] = 'VERB'

        for argument in template.arguments:
            name, value = get_name_value(argument)

            if name in ['база', '1'] and value is not None:
                opencorpora_tag['base'] = value
                universalD_tag['base'] = value
                continue

            if name in ['время', '2']:
                if value is None: continue
                opencorpora_tag['tag']['Tense'] = r_tense_opencorpora.get(value)
                universalD_tag['tag']['Tense'] = r_tense_universalD.get(value)
                continue

            if name == 'залог':
                continue

            if name in ['род', '3']:
                if value is None: continue
                opencorpora_tag['tag']['Gender'] = r_gender.get(value)
                universalD_tag['tag']['Gender'] = r_gender.get(value)
                continue

            if name in ['лицо', '4']:
                opencorpora_tag['tag']['Person'] = r_person_opencorpora.get(value)
                universalD_tag['tag']['Person'] = r_person_universalD.get(value)
                continue

            if name in ['число', '5'] and value is not None:
                opencorpora_tag['tag']['Number'] = r_number[value]
                universalD_tag['tag']['Number'] = r_number[value]
                continue

            if name in ['накл', '6'] and value is not None:
                continue

            if name == 'деепр':
                continue

            if name == 'прич':
                continue

            if name == 'кр':
                continue

            if name in ['помета', '7'] and value is not None:
                continue

            if name == 'форма':
                continue

            if name == 'слоги':
                continue

        return [[word_acc, opencorpora_tag, universalD_tag]]

    if template_name == 'conj ru':
        opencorpora_tag['pos'] = 'CONJ'
        universalD_tag['pos'] = 'CONJ'

        base = get_word_from_slogi(template)[0].replace('́', '')
        opencorpora_tag['base'] = base
        universalD_tag['base'] = base

        return [[opencorpora_tag, universalD_tag]]

    if 'прил ru' in template_name:
        opencorpora_tag['pos'] = 'ADJF'
        universalD_tag['pos'] = 'ADJ'

        base = get_word_from_slogi(template)[0].replace('́', '')
        opencorpora_tag['base'] = base
        universalD_tag['base'] = base

        for argument in template.arguments:
            name, value = get_name_value(argument)

            if name == 'тип':
                if value is None: continue
                if value == 'качественное':
                    if 'flags' in opencorpora_tag['tag']:
                        opencorpora_tag['tag']['flags'] += ',' + r_degree_opencorpora.get(value)
                    else:
                        opencorpora_tag['tag']['more'] = r_degree_opencorpora.get(value)
                    universalD_tag['tag']['Degree'] = r_degree_univarsalD.get(value)
                    continue
                raise Exception

            if name == 'степень':
                if value is None: continue
                raise Exception

        # склонения по падежу / числу
        parsed = wtp.parse(get_wikitext_api_expandtemplates(template.string))
        table = table_to_2d(BeautifulSoup(parsed.string.replace('<br>','\n'), 'lxml').table)

        _header = table.pop(0)
        assert _header[0].strip() == '[[падеж]]'
        assert _header[1].strip() == '[[падеж]]'
        assert _header[2].strip() == '[[единственное число|ед. ч.]]'
        assert _header[3].strip() == '[[единственное число|ед. ч.]]'
        assert _header[4].strip() == '[[единственное число|ед. ч.]]'
        assert _header[5].strip() == '[[множественное число|мн. ч.]]'
        _header = table.pop(0)
        assert _header[0].strip() == '[[падеж]]'
        assert _header[1].strip() == '[[падеж]]'
        assert 'мужской' in _header[2]
        assert 'средний' in _header[3]
        assert 'женский' in _header[4]
        assert _header[5].strip() == '[[множественное число|мн. ч.]]'

        for row in table:
            case = re.search(r'\[\[([а-яё. ]+)(\||\]\])', row[0]).group(1)
            assert case in r_case_opencorpora or 'краткая' in case
            anim = re.search(r'\[\[([а-яё. ]+)(\||\]\])', row[1]).group(1)
            assert anim in r_anim or anim in r_case_opencorpora or 'краткая' in case

            for i in range(4):
                words = None
                m = re.fullmatch(r'([́а-яёА-ЯЁ]+)', row[2+i])
                if m is None: m = re.search(r'>([́а-яёА-ЯЁ]+)<', row[2+i])

                if m is not None:
                    words = [m.group(1)]
                else:
                    if '—' in row[2+i]:
                        words = None
                    else:
                        splits = re.split(split_regex, row[2+i])
                        if len(splits) > 1:
                            words = splits
                        else:
                            raise Exception


                if words is not None:
                    opencorpora_tag_copy = copy.deepcopy(opencorpora_tag)
                    universalD_tag_copy = copy.deepcopy(universalD_tag)

                    if 'краткая' not in case:
                        opencorpora_tag_copy['tag']['Case'] = r_case_opencorpora[case]
                        universalD_tag_copy['tag']['Case'] = r_case_universalD[case]
                    else:
                        opencorpora_tag_copy['pos'] = 'ADJS'
                        universalD_tag_copy['tag']['Variant'] = 'Short'
                    opencorpora_tag_copy['tag']['Number'] = r_number['ед'] if i < 3 else r_number['мн']
                    universalD_tag_copy['tag']['Number'] = r_number['ед'] if i < 3 else r_number['мн']
                    if i < 3:
                        genders = {0: 'м', 1: 'с', 2: 'ж'}
                        opencorpora_tag_copy['tag']['Gender'] = r_gender[genders[i]]
                        universalD_tag_copy['tag']['Gender'] = r_gender[genders[i]]

                    if anim in r_anim:
                        opencorpora_tag_copy['tag']['Animacy'] = r_anim[anim]
                        universalD_tag_copy['tag']['Animacy'] = r_anim[anim]

                    variants.append([words, opencorpora_tag_copy, universalD_tag_copy])

        return variants

    if template_name == 'сущ-ru':
        opencorpora_tag['pos'] = 'NOUN'
        universalD_tag['pos'] = 'NOUN'

        for argument in template.arguments:
            name, value = get_name_value(argument)

            if name in ['слово', '1'] and value is not None:
                opencorpora_tag['base'] = value.replace('́', '')
                universalD_tag['base'] = value.replace('́', '')
                continue

            if name in ['индекс', '2'] and value is not None:
                data = value.split()[:-1]

                for d in data:
                    if d in r_gender:
                        opencorpora_tag['tag']['Gender'] = r_gender.get(d)
                        universalD_tag['tag']['Gender'] = r_gender.get(d)
                        continue

                    if d in r_anim:
                        opencorpora_tag['tag']['Animacy'] = r_anim.get(d)
                        universalD_tag['tag']['Animacy'] = r_anim.get(d)
                        continue
                continue

        # склонения по падежу / числу
        parsed = wtp.parse(get_wikitext_api_expandtemplates(template.string))
        table = parsed.tables[0].data()

        _header = table.pop(0)
        assert 'падеж' in _header[0]
        assert 'единственное' in _header[1]
        assert 'множественное' in _header[2]

        for row in table:
            case = re.search(r'\[\[([а-яё. ]+)(\||\]\])', row[0]).group(1)
            assert case in r_case_opencorpora

            for i in range(2):
                m = re.fullmatch(r'([́а-яёА-ЯЁ]+)', row[1+i])
                if m is None: m = re.search(r'>([́а-яёА-ЯЁ]+)<', row[1+i])

                if m is not None:
                    words = [m.group(1)]
                else:
                    if '—' in row[1+i]:
                        words = None
                    else:
                        splits = re.split(split_regex, row[1+i])
                        if len(splits) > 1:
                            words = splits
                        else:
                            raise Exception


                if words is not None:
                    opencorpora_tag_copy = copy.deepcopy(opencorpora_tag)
                    universalD_tag_copy = copy.deepcopy(universalD_tag)

                    opencorpora_tag_copy['tag']['Case'] = r_case_opencorpora[case]
                    universalD_tag_copy['tag']['Case'] = r_case_universalD[case]

                    opencorpora_tag_copy['tag']['Number'] = r_number['ед'] if i == 0 else r_number['мн']
                    universalD_tag_copy['tag']['Number'] = r_number['ед'] if i == 0 else r_number['мн']

                    variants.append([words, opencorpora_tag_copy, universalD_tag_copy])

        return variants

    if 'сущ ru' in template_name:
        opencorpora_tag['pos'] = 'NOUN'
        universalD_tag['pos'] = 'NOUN'

        base = get_word_from_slogi(template)[0].replace('́', '')
        opencorpora_tag['base'] = base
        universalD_tag['base'] = base

        data = template_name.split()[2:-1]

        for d in data:
            if d in r_gender:
                opencorpora_tag['tag']['Gender'] = r_gender.get(d)
                universalD_tag['tag']['Gender'] = r_gender.get(d)
                continue

            if d in r_anim:
                opencorpora_tag['tag']['Animacy'] = r_anim.get(d)
                universalD_tag['tag']['Animacy'] = r_anim.get(d)
                continue

            print(template_name, d)

        # склонения по падежу / числу
        parsed = wtp.parse(get_wikitext_api_expandtemplates(template.string))
        table = parsed.tables[0].data()
        _header = table.pop(0)
        assert 'падеж' in _header[0]
        assert 'единственное' in _header[1]
        assert 'множественное' in _header[2]

        for row in table:
            case = re.match(r'\[\[([а-яё.]+)(\||\]\])', row[0]).group(1)
            assert case in r_case_opencorpora

            for i in range(2):
                m = re.fullmatch(r'([́а-яёА-ЯЁ]+)', row[1+i])
                if m is None: m = re.search(r'>([́а-яёА-ЯЁ]+)<', row[1+i])

                if m is not None:
                    words = [m.group(1)]
                else:
                    if '—' in row[1+i]:
                        words = None
                    else:
                        splits = re.split(split_regex, row[1+i])
                        if len(splits) > 1:
                            words = splits
                        else:
                            raise Exception


                if words is not None:
                    opencorpora_tag_copy = copy.deepcopy(opencorpora_tag)
                    universalD_tag_copy = copy.deepcopy(universalD_tag)

                    opencorpora_tag_copy['tag']['Case'] = r_case_opencorpora[case]
                    universalD_tag_copy['tag']['Case'] = r_case_universalD[case]

                    opencorpora_tag_copy['tag']['Number'] = r_number['ед'] if i == 0 else r_number['мн']
                    universalD_tag_copy['tag']['Number'] = r_number['ед'] if i == 0 else r_number['мн']

                    variants.append([words, opencorpora_tag_copy, universalD_tag_copy])

        return variants

    if 'Фам ru' in template_name:
        # Фамилии, скип
        return []

    if 'гл ru' in template_name:
        opencorpora_tag['pos'] = 'INFN'
        universalD_tag['pos'] = 'VERB'
        universalD_tag['tag']['VerbForm'] = 'Inf'

        base = get_word_from_slogi(template)[0].replace('́', '')
        opencorpora_tag['base'] = base
        universalD_tag['base'] = base

        for argument in template.arguments:
            name, value = get_name_value(argument)

            if name == 'НП':
                opencorpora_tag['tag']['TRns'] = 'intr' if value == '1' else 'tran'
                continue

            if name == 'соотв':
                if value is None:
                    opencorpora_tag['tag']['ASpc'] = 'perf'
                    universalD_tag['tag']['Aspect'] = 'Perf'
                else:
                    opencorpora_tag['tag']['ASpc'] = 'impf'
                    universalD_tag['tag']['Aspect'] = 'Imp'
                continue

        variants.append([word_acc, copy.deepcopy(opencorpora_tag), copy.deepcopy(universalD_tag)])
        opencorpora_tag['pos'] = 'VERB'
        universalD_tag['tag'].pop('VerbForm')

        # склонения по падежу / числу
        parsed = wtp.parse(get_wikitext_api_expandtemplates(template.string))
        table = parsed.tables[0].data()
        _header = table.pop(0)
        assert 'настоящее' in _header[1]
        assert 'прошедшее' in _header[2]
        assert 'повелительное' in _header[3]

        for row in table:
            person = re.match(r'\[\[([а-яё.]+)(\||\]\])', row[0]).group(1)
            assert person in r_person_opencorpora

            for i in range(3):
                m = re.fullmatch(r'([́а-яёА-ЯЁ]+)', row[1+i])
                if m is None: m = re.search(r'>([́а-яёА-ЯЁ]+)<', row[1+i])

                if m is not None:
                    words = [m.group(1)]
                else:
                    if '—' in row[1+i]:
                        words = None
                    else:
                        splits = re.split(split_regex, row[1+i])
                        if len(splits) > 1:
                            words = splits
                        else:
                            raise Exception


                if words is not None:
                    opencorpora_tag_copy = copy.deepcopy(opencorpora_tag)
                    universalD_tag_copy = copy.deepcopy(universalD_tag)

                    opencorpora_tag_copy['tag']['Person'] = r_person_opencorpora[person]
                    universalD_tag_copy['tag']['Person'] = r_person_universalD[person]

                    opencorpora_tag_copy['tag']['Number'] = r_number['ед'] if i == 0 else r_number['мн']
                    universalD_tag_copy['tag']['Number'] = r_number['ед'] if i == 0 else r_number['мн']

                    variants.append([words, opencorpora_tag_copy, universalD_tag_copy])

        table = table_to_2d(BeautifulSoup('<table>' + parsed.string.replace('<br>', '\n') + '</table>', 'lxml').table)

        for row in table:
            if 'причастие' in row[0]:
                tense = 'наст' if 'настоящего' in row[0] else 'пр'

                opencorpora_tag_copy = copy.deepcopy(opencorpora_tag)
                universalD_tag_copy = copy.deepcopy(universalD_tag)

                opencorpora_tag_copy['pos'] = 'PRTF'

                opencorpora_tag_copy['tag']['Tense'] = r_tense_opencorpora[tense]
                universalD_tag_copy['tag']['Tense'] = r_tense_universalD[tense]

            if 'деепричастие' in row[0]:
                tense = 'наст' if 'настоящего' in row[0] else 'пр'

                opencorpora_tag_copy = copy.deepcopy(opencorpora_tag)
                universalD_tag_copy = copy.deepcopy(universalD_tag)

                opencorpora_tag_copy['pos'] = 'GRND'
                universalD_tag_copy['tag']['VerbForm'] = 'Conv'

                opencorpora_tag_copy['tag']['Tense'] = r_tense_opencorpora[tense]
                universalD_tag_copy['tag']['Tense'] = r_tense_universalD[tense]

            if 'будущее' in row[0]:
                tense = 'буд'

                opencorpora_tag_copy = copy.deepcopy(opencorpora_tag)
                universalD_tag_copy = copy.deepcopy(universalD_tag)

                opencorpora_tag_copy['tag']['Tense'] = r_tense_opencorpora[tense]
                universalD_tag_copy['tag']['Tense'] = r_tense_universalD[tense]

                row[1] = row[1].replace('буду/будешь…', '').strip()

            words = []
            for w in re.split(split_regex, row[1]):
                m = re.search(r'\|([́а-яёА-ЯЁ]+)\]\]', w)
                if m is None: m = re.fullmatch(r'([́а-яёА-ЯЁ]+)', w)
                words.append(m.group(1))

            variants.append([words, opencorpora_tag_copy, universalD_tag_copy])

        return variants

    print(template_name)
    raise Exception()