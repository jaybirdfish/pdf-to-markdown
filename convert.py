from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.pdfdevice import PDFDevice
from pdfminer.layout import LAParams
from pdfminer.layout import LTFigure
from pdfminer.layout import LTTextBox
from pdfminer.layout import LTTextLine
from pdfminer.layout import LTTextBoxHorizontal
from pdfminer.layout import LTTextLineHorizontal
from pdfminer.layout import LTLine
from pdfminer.layout import LTRect
from pdfminer.layout import LTImage
from pdfminer.layout import LTCurve
from pdfminer.converter import PDFPageAggregator
from pile import Pile


def is_overlap(top, bottom, obj):
	return (bottom - 1.0) <= obj.y0 <= (top + 1.0) or \
		   (bottom - 1.0) <= obj.y1 <= (top + 1.0)


def calc_top_bottom(objects):
	top = float('-inf')
	bottom = float('inf')
	for obj in objects:
		top = max(top, obj.y1)
		bottom = min(bottom, obj.y0)
	return top, bottom


def find_near_verticals(start, verticals):
	near_verticals = [start]
	top = start.y1
	bottom = start.y0
	for vertical in verticals:
		if vertical == start:
			continue
		if is_overlap(top, bottom, vertical):
			near_verticals.append(vertical)
			top, bottom = calc_top_bottom(near_verticals)
	return near_verticals


def find_included(top, bottom, objects):
	included = []
	for obj in objects:
		if is_overlap(top, bottom, obj):
			included.append(obj)
	return included


def find_tables(pile):
	tables = []
	visited = set()
	for vertical in pile.verticals:
		if vertical in visited:
			continue

		near_verticals = find_near_verticals(vertical, pile.verticals)
		top, bottom = calc_top_bottom(near_verticals)
		included_horizontals = find_included(top, bottom, pile.horizontals)
		included_texts = find_included(top, bottom, pile.texts)

		table = Pile()
		table.verticals = near_verticals
		table.horizontals = included_horizontals
		table.texts = included_texts

		tables.append(table)
		visited.update(near_verticals)
	return tables


def find_paragraphs(pile, tables):
	tops = []
	for table in tables:
		top, bottom = calc_top_bottom(table.verticals)
		tops.append(top)

	all_table_texts = set()
	for table in tables:
		all_table_texts.update(table.texts)

	num_slots = len(tables) + 1
	paragraphs = [Pile() for idx in range(num_slots)]
	for text in pile.texts:
		if text in all_table_texts:
			continue
		for idx, table in enumerate(tables):
			if text.y0 > tops[idx]:
				paragraphs[idx].texts.append(text)
				break

	paragraphs = filter(None, paragraphs)

	return paragraphs


def split_piles(big_pile):
	tables = find_tables(big_pile)
	paragraphs = find_paragraphs(big_pile, tables)

	small_piles = sorted(tables + paragraphs, reverse=True, key=lambda x: x.texts[0].y0)

	return small_piles


def gen_html(pile):
	html = ''

	page_height = 800 # for flipping the coordinate

	html += '<meta charset="utf8" />'
	html += '<svg width="100%" height="100%">'

	# flip coordinate
	html += '<g transform="translate(0, {}) scale(1, -1)">'.format(page_height)

	rect = '<rect width="{width}" height="{height}" x="{x}" y="{y}" fill="{fill}"><title>{text}</title></rect>'

	for text in pile.texts:
		info = {
			'width': text.x1 - text.x0,
			'height': text.y1 - text.y0,
			'x': text.x0,
			'y': text.y0,
			'text': text.get_text().encode('utf8'),
			'fill': 'green',
		}
		html += rect.format(**info)

	for vertical in pile.verticals:
		info = {
			'width': 1,
			'height': vertical.y1 - vertical.y0,
			'x': vertical.x0,
			'y': vertical.y0,
			'text': '',
			'fill': 'blue',
		}
		html += rect.format(**info)

	for horizontal in pile.horizontals:
		info = {
			'width': horizontal.x1 - horizontal.x0,
			'height': 1,
			'x': horizontal.x0,
			'y': horizontal.y0,
			'text': '',
			'fill': 'red',
		}
		html += rect.format(**info)

	html += '</g>'
	html += '</svg>'

	return html


def gen_paragraph_markdown(pile):
	markdown = ''
	for text in pile.texts:
		content = text.get_text().encode('utf8').strip()
		markdown += content + '\n\n'
	return markdown


def gen_table_markdown(pile):
	return ''


def gen_markdown(pile):
	pile_type = pile.get_type()
	if pile_type == 'paragraph':
		return gen_paragraph_markdown(pile)
	elif pile_type == 'table':
		return gen_table_markdown(pile)
	else:
		raise Exception('unsupported markdown type')


def write_file(filename, string):
	with open(filename, 'w') as fw:
		fw.write(string)

def parse_page(layout):
	pile = Pile()

	objstack = list(reversed(list(layout)))
	while objstack:
		b = objstack.pop()
		if type(b) in [LTFigure, LTTextBox, LTTextLine, LTTextBoxHorizontal]:
			objstack.extend(reversed(list(b)))
		elif type(b) == LTTextLineHorizontal:
			pile.texts.append(b)
		elif type(b) == LTRect:
			if b.x1 - b.x0 < 1.0:
				pile.verticals.append(b)
			elif b.y1 - b.y0 < 1.0:
				pile.horizontals.append(b)
			elif 15.0 < b.y1 - b.y0 < 18.0: # grey blocks
				pass
			else:
				raise Exception('strange lines')
		elif type(b) == LTImage:
			pass
		elif type(b) == LTCurve:
			pass
		else:
			assert False, "Unrecognized type: %s" % type(b)

	return pile


def main():
	target_page = 13

	parser = PDFParser(open('neihu.pdf', 'rb'))
	document = PDFDocument(parser)
	laparams = LAParams()
	rsrcmgr = PDFResourceManager()
	device = PDFPageAggregator(rsrcmgr, laparams=laparams)
	interpreter = PDFPageInterpreter(rsrcmgr, device)

	for page in PDFPage.create_pages(document):
		interpreter.process_page(page)
		layout = device.get_result()

		if layout.pageid < target_page:
			continue
		elif layout.pageid > target_page:
			break

		print 'layout.pageid:', layout.pageid

		pile = parse_page(layout)
		piles = split_piles(pile)

		print 'len(piles):', len(piles)

		for idx, pile in enumerate(piles):
			filename = 'part{}.html'.format(idx)
			string = gen_html(pile)
			write_file(filename, string)

			filename = 'part{}.md'.format(idx)
			string = gen_markdown(pile)
			write_file(filename, string)


if __name__ == '__main__':
	main()

