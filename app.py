import sys, re, json, shutil
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
from bs4 import BeautifulSoup
import pystache as mustache
from PIL import Image, ImageDraw, ImageFont

class Project:
    ROOT = Path(__file__).parent
    text_dir = ROOT / "src" / "text"
    tmpl_dir = ROOT / "src" / "epub"
    dist_dir = ROOT / "dist"
    text_files = text_dir.glob('*.xhtml')
    tmpl_files = tmpl_dir.rglob('*')
    templates = ('package.opf', 'toc.ncx', 'Content/toc.xhtml')
    tmpl_suffixes = ('.opf', '.xhtml', '.ncx')
    tmpl_section = 'section.xhtml'
    section_dir_name = 'text'
    section_suffix = '.xhtml'
    chapter_section_name = 'chapters'
    cover_src = ROOT / "src" / "cover" / "cover.png"
    cover_font = ROOT / "src" / "cover" / "EBGaramond-SemiBold.ttf"
    words_per_page = 260
    name = "Tao Te Ching - Lao Tzu [Translations]"
    default_prefix = '00'

def is_template(path):
    for p in Project.templates:
        if path.samefile(Project.tmpl_dir / Path(p)):
            return True
    return False

class Builder:
    def __init__(self):
        pass

def main():
    book = Book()
    for p in Project.text_files:
        tr = parse(p)
        book.add(tr)
    build(book)


class SectionType(Enum):
    dedication = 0
    foreword = 1
    preface = 2
    introduction = 3
    epigraph = 4
    prologue = 5
    chapter = 6
    epilogue = 7
    afterword = 8
    endnotes = 9
    appendix = 10
    bibliography = 11
    acknowledgments = 12
    @classmethod
    def create(cls, name):
        for item in cls:
            if name == item.name:
                return item
        raise ValueError(name)

'''
./dist/
    Tao Te Ching - Lao Tzu [Translations]/
        Content/
            01 - Stephen Mitchell/
                chapters.xhtml
                introduction.xhtml
                titlepage.xhtml
        package.opf
        toc.ncx
'''

# prefix - translator/id.extension

class EpubSectionDoc:
    header_ = '''
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xml:lang="{language}" lang="{language}" xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>{title}</title>
    <meta charset="utf-8"/>
    <link href="style/base.css" rel="stylesheet" type="text/css"/>
    <link href="style/main.css" rel="stylesheet" type="text/css"/>
</head>
<body epub:type="bodymatter">
'''
    footer_ = '''
</body>
</html>
'''
    def __init__(self, path, language, title):
        self.path = path
        self.file = None
        self.language = language
        self.title = title
    def acquire(self):
        if not self.file:
            self.file = open(self.path, 'w', encoding='utf-8', newline='')
            self.file.write(self.header + "\n")
        return self.file
    def append(self, value):
        self.acquire().write(value + "\n")
    @property
    def header(self):
        return self.header.format(
            language=self.language,
            title=self.title
        ).strip()
    @property
    def footer(self):
        return self.footer_.strip()
    def close(self):
        if self.file:
            self.file.write("\n" + self.footer + "\n")
            self.file.close()
            self.file = None
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        self.close()
    def __del__(self):
        self.close()

class Metadata:
    uuid = "a8f161cf-2ea4-4d4c-bdc5-1be41d7b9fd3"
    language = "en"
    title = "Tao Te Ching"
    author = "Lao Tzu"

class Book(Metadata):
    """Represents the whole book"""
    def __init__(self):
        self.date_modified = date_modified()
        self.date = date()
        self.translations = []
    def add(self, translation):
        translation.book = self
        self.translations.append(translation)
    @property
    def word_count(self):
        count = 0
        for tr in self.translations:
            count += tr.word_count
        return count
    @property
    def number_of_pages(self):
        return self.word_count // Project.words_per_page

class Translation:
    """Represents a translation document"""
    def __init__(self):
        self.book = None
        self.language = None
        self.title = None
        self.author = None
        self.translator = None
        self.year = None
        self.prefix = Project.default_prefix
        self.sections = []
    def __str__(self):
        return f'{self.prefix} - {self.translator} ({self.year})'
    @property
    def dirname(self):
        return f'{self.prefix} - {self.translator}'
    @property
    def path(self):
        return Path(self.dirname)
    def chapters(self):
        for s in self.sections:
            if s.type is SectionType.chapter:
                yield s
    def non_chapters(self):
        for s in self.sections:
            if s.type is not SectionType.chapter:
                yield s
    @property
    def word_count(self):
        counter = 0
        for s in self.sections:
            if s.element:
                for line in s.element.stripped_strings:
                    counter += len(re.findall(r'\w+', line))
        return counter

class Section:
    """Represents a translation section or chapter"""
    def __init__(self, type_):
        self.translation = None
        self.language = None
        self.type = type_
        self.number = 1
        self.element = None
    @property
    def id(self):
        if self.element:
            return self.element.get('id')
        return None
    @property
    def title(self):
        if self.element:
            return self.element.get('title')
        return None
    @property
    def body(self):
        if self.element:
            return str(self.element)
        return ""
    @property
    def order(self):
        return str(self.type.value) + str(self.number)
    @property
    def filename(self):
        return (Project.chapter_section_name if self.is_chapter() else self.id) \
            + Project.section_suffix
    @property
    def path(self):
        if not self.translation:
            return Path(self.filename)
        return Path(self.translation.dirname) / self.filename
    def __str__(self):
        return self.body
    def is_chapter(self):
        return self.type is SectionType.chapter
    def has_id(self, id_):
        if id_ == self.id:
            return True
        return bool(self.element.find(id=id_))

def date_modified():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def date():
    return datetime.now().strftime("%Y-%m-%d")

def build_template(book, src, dst):
    with open(src, 'r', encoding='utf-8') as fp:
        tmpl = fp.read()
        rendered = mustache.render(tmpl, book)
        with open(dst, 'w', encoding='utf-8', newline='') as dfp:
            dfp.write(rendered)

def build_book(book, dst):
    cdst = dst / 'Content'
    for translation in book.translations:
        first_chapter = None
        for ch in translation.chapters():
            first_chapter = ch
            break
        if not first_chapter:
            continue
        tdst = cdst / translation.dirname
        path = tdst / first_chapter.filename
        path.mkdir(parents=True, exist_ok=True)
        language = first_chapter.language or translation.language
        with EpubSectionDoc(path, language, translation.title) as doc:
            for ch in translation.chapters():
                doc.append(ch.body)
        for section in translation.non_chapters():
            path = tdst / section.filename
            path.mkdir(parents=True, exist_ok=True)
            language = section.language or translation.language
            title = f'{section.title} - {translation.title}'
            with EpubSectionDoc(path, language, title) as doc:
                doc.append(section.body)

def build_epub(source):
    root = source.parent
    name = source.name
    path = root / (name + ".epub")
    with ZipFile(path, 'w', compression=ZIP_DEFLATED, compresslevel=4) as epub:
        for file in source.rglob('*'):
            epub.write(file, file.relative_to(source))

def build(book):
    destination = Project.dist_dir / Project.name
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for src in Project.tmpl_files:
        dst = destination / (src.relative_to(Project.tmpl_dir))
        dst.parent.mkdir(parents=True, exist_ok=True)
        if is_template(src):
            build_template(book, src, dst)
        else:
            shutil.copyfile(src, dst)
    build_book(book, destination)
    #build_epub(destination)

def process(translation):
    def extract_id(a):
        href = a.get('href', '').strip()
        return (href[1:] if href[0] == '#' else href) if href else ''
    for section in translation.sections:
        for a in section.element.find_all('a'):
            href_id = extract_id(a)
            if len(href_id) == 0:
                continue
            if href_id == section.id:
                continue
            for s in translation.sections:
                if s is section:
                    continue
                if s.has_id(href_id):
                    a['href'] = f'{s.filename}#{href_id}'
                    break

def parse(path, default_metadata=None):
    def set_metadata(translation, soup):
        if default_metadata:
            for key in ('language', 'title', 'author'):
                if value := getattr(default_metadata, key, None):
                    setattr(translation, key, value)
        translation.language = soup.html.get('lang')
        translation.title = soup.head.title.string
        for meta in soup.head.find_all('meta'):
            if name := meta.get('name'):
                if hasattr(translation, name):
                    if (value := meta.get('content')) is not None:
                        setattr(translation, name, value)
    def finalize_section(section):
        section.language = section.element.get('lang')
        if not section.element.get('title'):
            section.element['title'] = str(section.number) \
                if section.is_chapter() else section.id.title()
    def create_sections(soup):
        for element in soup.body('section', recursive=False):
            type_ = element.get('epub:type')
            if not type_:
                raise Exception(f'Section without "epub:type" attribute')
            type_ = SectionType.create(type_)
            if not element.get('id'):
                if type_ is SectionType.chapter:
                    raise Exception(f'Chapter section without "id" attribute')
                element['id'] = type_.name
            section = Section(type_)
            section.element = element.extract()
            finalize_section(section)
            yield section
    def create_translation(soup):
        translation = Translation()
        set_metadata(translation, soup)
        for section in create_sections(soup):
            if not section.language:
                section.language = translation.language
            translation.sections.append(section)
        translation.sections.sort(key=lambda s: s.order)
        return translation
    with open(path, 'r', encoding='utf-8') as fp:
        soup = BeautifulSoup(fp, 'lxml')
        translation = create_translation(soup)
        if m := re.match(r'(\d+) - ', Path(path).name):
            translation.prefix = m[1]
        return translation

if __name__ == '__main__':
    main()



class RereferceId:
    CHAPTER = 'ch'
    FOOTNOTE = 'fn'
    ENDNOTE = 'en'
    NOTEREF = 'nr'
    BACKLINK = 'bl'
    prefixes = (CHAPTER, FOOTNOTE, ENDNOTE, NOTEREF, BACKLINK)
    secmap = {
        'fn': 'endnotes',
        'en': 'endnotes',
        'nr': 'chapter'
    }
    def __init__(self, value):
        self.prefix = None
        self.snumber = None
        self.sindex = None
        self.parse(value)
    @property
    def number(self):
        return None if self.snumber is None else int(self.snumber)
    @property
    def index(self):
        return None if self.sindex is None else int(self.sindex)
    def is_chapter(self):
        return self.prefix == self.CHAPTER
    def is_note(self):
        return self.prefix in (self.FOOTNOTE, self.ENDNOTE)
    def __str__(self):
        result = f"{self.prefix}-{self.snumber}"
        if self.snumber is not None:
            return f"{result}-{self.sindex}"
        return result
    def parse(self, value):
        prefixes = '|'.join(self.prefixes)
        m = re.match(fr'^({prefixes})-(\d+)(?:-(\d+))?$', value)
        if not m:
            raise Exception(f'Reference id value "{value}" is not valid')
        self.prefix = m[1]
        self.snumber = m[2]
        self.sindex = m[3]


'''
def create_cover(dst_dir, translation):
    text = translation.translator
    src = Project.cover_src
    dst = Path(dst_dir) / (src.stem + '.jpg')
    with Image.open(src) as im:
        if text:
            font_size = int(max(16, min(128, 20 + 108 * (15/len(text)))))
            font = ImageFont.truetype(str(Project.cover_font), size=font_size)
            dw = ImageDraw.Draw(im)
        dw.text((536, 1280), text, fill=(255, 255, 255), anchor="mm", font=font)
        im.convert("RGB").save(dst)
'''

'''
def create_directory_structure(name):
    dir_ = Project.dist_dir / name
    if dir_.exists():
        shutil.rmtree(dir_)
    for fname, data in EpubPackage.container_files:
        fpath = dir_ / fname
        if not fpath.parent.exists():
            fpath.parent.mkdir(parents=True)
        with open(fpath, 'w', encoding='utf-8') as fp:
            fp.write(data.lstrip())
    dir_ = dir_ / EpubPackage.content_dir
    sdir = dir_ / Project.section_dir_name
    sdir.mkdir(parents=True, exist_ok=True)
    return dir_
'''

'''
def build(translation):
    dir_ = create_directory_structure(translation.name)
    def write(fname, content):
        output = dir_ / Path(fname)
        with open(output, 'w', encoding='utf-8') as of:
            of.write(content)
    def is_tmpl(name):
        for suffix in Project.tmpl_suffixes:
            if name.endswith(suffix):
                return True
        return False
    section_template = None
    for path in Project.tmpl_files:
        if not is_tmpl(path.name):
            shutil.copyfile(path, dir_ / path.name)
        else:
            with open(path, 'r', encoding='utf-8') as f:
                template = f.read()
                if path.name == Project.tmpl_section:
                    section_template = template
                    continue
                rendered = mustache.render(template, translation)
                write(path.name, rendered)
    if section_template:
        for section in translation.sections:
            rendered = mustache.render(section_template, section)
            write(section.path, rendered)
    create_cover(dir_, translation)
    create_epub(translation.name)
'''

'''

SECTIONS = {
    'dedication': None,
    'foreword': 'Foreword',
    'preface': 'Preface',
    'introduction': 'Introduction',
    'epigraph': None,
    'prologue': 'Prologue',
    'chapter': None,
    'epilogue': 'Epilogue',
    'afterword': 'Afterword',
    'footnotes': 'Notes',
    'endnotes': 'Notes',
    'appendix': 'Appendix',
    'acknowledgments': 'Acknowledgments'
}


class Processor:
    def __init__(self, soup):
        self.soup = soup
        self.processed = False
        self.sids = {}
    def __iter__(self):
        return self.sections()
    def sections(self):
        self.process()
        for section in self._sections():
            so = Section(section['epub:type'], section['id'])
            so.title = section['title']
            so.language = section.get('lang') or None
            so.chapter = section.get('data-number')
            so.word_count = self.get_word_count(section)
            for a in section.find_all('a'):
                if href := a.get('href'):
                    shref = self.make_section_href(href)
                    if shref:
                        a['href'] = shref
            so.body = str(section)
            yield so
    def _sections(self):
        for section in self.soup.body('section', recursive=False):
            type_ = section.get('epub:type')
            if not type_:
                raise Exception(f'Section without "epub:type" attribute')
            type_ = SectionType.create(type_)
            yield type_, section
    def get_word_count(self, section):
        counter = 0
        for line in section.stripped_strings:
            counter += len(re.findall(r'\w+', line))
        return counter
    def make_section_href(self, href):
        if '#' in href:
            href = href.split('#', 1)[1]
        for sid, ids in self.sids.items():
            if href in ids or href == sid:
                return f'{sid}{Project.section_suffix}#{href}'
        return None
    def get_heading_title(self, section):
        if section['epub:type'] == 'chapter':
            return '– ' + section['title'] + ' –'
        if SECTIONS[section['epub:type']] is None:
            return None
        return section['title']
    def set_attributes(self, section):
        type_ = section['epub:type']
        id_ = section.get('id')
        if not id_:
            id_ = type_
            section['id'] = id_
        title = section.get('title')
        if type_ == 'chapter':
            refid = RereferceId(id_)
            assert refid.is_chapter()
            section['data-number'] = refid.number
            if not title:
                section['title'] = str(refid.number)
        elif not title:
            section['title'] = SECTIONS[type_] or id_.title()
        return type_, id_
    def process(self):
        if self.processed:
            return
        for section in self._sections():
            type_, id_ = self.set_attributes(section)
            self.sids[id_] = [e.get('id') for e in section.find_all(id=True)]
            self.insert_heading(section)
            if type_ in ('footnotes', 'endnotes'):
                self.insert_notes_headings(section)
        self.processed = True
    def insert_heading(self, section):
        if section.h1 or section.h2:
            return
        title = self.get_heading_title(section)
        if not title:
            return
        h2_tag = self.soup.new_tag('h2')
        css_class = 'chapter' if section['epub:type'] == 'chapter' else 'chapter-big'
        h2_tag.string = title
        h2_tag['class'] = [css_class,]
        section.insert(0, h2_tag)
        section.insert(0, "\n")
    def insert_notes_headings(self, section):
        def is_note(el):
            if el.get('epub:type') not in ('footnote', 'endnote'):
                return False
            return el.has_attr('id')
        seen = {}
        for el in section.find_all(is_note, recursive=False):
            refid = RereferceId(el.get('id'))
            assert refid.is_note()
            if refid.number in seen:
                continue
            seen[refid.number] = True
            h3_tag = self.soup.new_tag('h3')
            h3_tag.string = str(refid.number)
            el.insert_before(h3_tag)
            el.insert_before("\n")
'''
