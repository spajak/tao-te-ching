import sys, re, json, shutil
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
from bs4 import BeautifulSoup
import pystache as mustache
from PIL import Image, ImageDraw, ImageFont

def main():
    id_ = '01 - Stephen Mitchell.xhtml'
    for f in Project.text_files:
        if f.name == id_:
            tr = Translations().load(f)
            build(tr)

class Project:
    ROOT = Path(__file__).parent
    text_dir = ROOT / "src" / "text"
    tmpl_dir = ROOT / "src" / "epub"
    dist_dir = ROOT / "dist"
    text_files = text_dir.glob('*.xhtml')
    tmpl_files = tmpl_dir.glob('*.*')
    tmpl_suffixes = ('.opf', '.xhtml', '.ncx')
    tmpl_section = 'section.xhtml'
    cover_src = ROOT / "src" / "cover" / "cover.png"
    cover_font = ROOT / "src" / "cover" / "EBGaramond-SemiBold.ttf"
    metadata = ROOT / "src" / "metadata.json"
    words_per_page = 260

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

def get_section_order(type_):
    if type_ not in SECTIONS:
        raise Exception(f'Section type "{type_}" is not valid')
    idx = list(SECTIONS.keys()).index(type_)
    idx = str(idx).rjust(len(SECTIONS), '0')
    return idx

class Section:
    """Represents a translation section or chapter"""
    def __init__(self, type_, id_):
        self.type = type_
        self.id = id_
        self.title = None
        self.language = None
        self.chapter = None
        self.body = None
        self.word_count = 0
    @property
    def order(self):
        return get_section_order(self.type) + self.id
    @property
    def label(self):
        return self.title if self.title else self.id.title()
    @property
    def html_title(self):
        return self.label

class Translation:
    """Represents a translation document"""
    def __init__(self, uuid):
        self.uuid = uuid
        self.language = "en"
        self.title = "Tao Te Ching"
        self.author = "Lao Tzu"
        self.translator = None
        self.year = None
        self.sections = []
        self.items = []
        self.toc_title = None
        self.cover_label = None
        self.source = "https://github.com/spajak/tao-te-ching"
        self.date_modified = date_modified()
        self.publisher = "Home"
        self.date = date()
        self.subjects = []
        self.series = None
        self.description = None
        self.number_of_pages = 0
        self.word_count = 0
    @property
    def name(self):
        return "{} by {} - {}".format(
            self.title,
            self.author,
            self.translator
        )

class EpubPackage:
    """Represents epub package and its structure"""
    container_xml = """
<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
    <rootfiles>
        <rootfile full-path="Content/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>
"""
    MIMETYPE = "mimetype"
    content_dir = 'Content'
    container_files = (
        ('META-INF/container.xml', container_xml),
        (MIMETYPE, 'application/epub+zip')
    )

def date_modified():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def date():
    return datetime.now().strftime("%Y-%m-%d")

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
    dir_.mkdir(parents=True, exist_ok=True)
    return dir_

def create_epub(name):
    path = Project.dist_dir / name
    zip_path = path.with_suffix('.epub')
    with ZipFile(zip_path, 'w', compression=ZIP_DEFLATED, compresslevel=4) as epub:
        epub.write(path / EpubPackage.MIMETYPE, EpubPackage.MIMETYPE, compress_type=ZIP_STORED)
        for file in path.rglob('*'):
            if file.name == EpubPackage.MIMETYPE:
                continue
            epub.write(file, file.relative_to(path))

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

def build(translation):
    dir_ = create_directory_structure(translation.name)
    def write(fname, content):
        output = dir_ / fname
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
            write(section.id + '.xhtml', rendered)
    create_cover(dir_, translation)
    create_epub(translation.name)

class RereferceId:
    CHAPTER = 'ch'
    FOOTNOTE = 'fn'
    ENDNOTE = 'en'
    NOTEREF = 'nr'
    BACKLINK = 'bl'
    prefixes = (CHAPTER, FOOTNOTE, ENDNOTE, NOTEREF, BACKLINK)
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

class Processor:
    def __init__(self, soup, default_lang=None):
        self.soup = soup
        self.default_lang = default_lang
        self.processed = False
    def sections(self):
        self.process()
        for section in self.soup.body('section', recursive=False):
            so = Section(section['epub:type'], section['id'])
            so.title = section['title']
            so.language = section.get('lang') or self.default_lang
            so.chapter = section.get('data-number')
            so.word_count = self.get_word_count(section)
            so.body = str(section)
            yield so
    def get_word_count(self, section):
        counter = 0
        for line in section.stripped_strings:
            counter += len(re.findall(r'\w+', line))
        return counter
    def get_heading_title(self, section):
        if section['epub:type'] == 'chapter':
            return '– ' + section['title'] + ' –'
        if SECTIONS[section['epub:type']] is None:
            return None
        return section['title']
    def set_attributes(self, section):
        type_ = section['epub:type']
        if type_ not in SECTIONS:
            raise Exception(f'Section type "{type_}" is not valid')
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
        for section in self.soup.body('section', recursive=False):
            type_, id_ = self.set_attributes(section)
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
    def insert_footnotes(self, section):
        pass
    def insert_notes_headings(self, section):
        def is_note(el):
            if el.get('epub:type') not in ('footnote', 'endnote'):
                return False
            return el.has_attr('id')
        for el in section.find_all(is_note, recursive=False):
            refid = RereferceId(el.get('id'))
            assert refid.is_note()
            h3_tag = self.soup.new_tag('h3')
            h3_tag.string = str(refid.number)
            el.insert_before(h3_tag)
            el.insert_before("\n")

class Translations:
    def __init__(self, insert_titles=True, insert_footnotes=False):
        self.insert_titles = insert_titles
        self.insert_footnotes = insert_footnotes
        with open(Project.metadata) as md:
            self.metadata = json.load(md)
    def get_default_metadata(self, title, author=None, language=None):
        for md in self.metadata:
            if md['title'] != title:
                continue
            if author and 'author' in md and md['author'] != author:
                continue
            if language and 'language' in md and md['language'] != language:
                continue
            return md.copy()
        return {}
    def extract_metadata(self, soup):
        metadata = {
            'language': soup.html.get('lang'),
            'title': soup.head.title.string
        }
        for meta in soup.head.find_all('meta'):
            if name := meta.get('name'):
                if (value := meta.get('content')) is not None:
                    metadata[name] = value
        defaults = self.get_default_metadata(
            metadata['title'],
            metadata['author'],
            metadata['language']
        )
        for k, v in defaults.items():
            if k not in metadata:
                metadata[k] = v
        return metadata
    def get_items_from_sections(self, sections):
        items = []
        for section in sections:
            items.append({
                'id': section.id,
                'label': section.label,
                'path': section.id + '.xhtml'
            })
        return items
    def create_record(self, metadata):
        record = Translation(metadata['uuid'])
        for k, v in metadata.items():
            if k.startswith('_'):
                continue
            if hasattr(record, k) and k != 'uuid':
                setattr(record, k, v)
        return record
    def load(self, path):
        with open(path, 'r', encoding='utf-8') as fp:
            soup = BeautifulSoup(fp, 'lxml')
            metadata = self.extract_metadata(soup)
            record = self.create_record(metadata)
            proc = Processor(soup, record.language)
            sections = []
            word_count = 0
            for section in proc.sections():
                sections.append(section)
                word_count += section.word_count
            sections.sort(key=lambda s: s.order)
            record.sections = sections
            if not record.word_count:
                record.word_count = str(word_count)
            if not record.number_of_pages:
                record.number_of_pages = str(int(record.word_count) // Project.words_per_page)
            record.items = self.get_items_from_sections(sections)
            return record

if __name__ == '__main__':
    main()
