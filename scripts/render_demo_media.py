"""Render native plugin dialogs using recorded, genuine API results.
No requests are made here. The walkthrough is edited, not a continuous recording.
"""
import copy,json,os,runpy
from pathlib import Path
from qt.core import (QMainWindow,QTableView,QStandardItemModel,QStandardItem,QAction,
                     QDialog,QVBoxLayout,QApplication,Qt,QImage,QPainter,QColor,QFont,QRect,
                     QSize,QPoint)
from calibre.gui2 import Application
from calibre.db.legacy import LibraryDatabase
from calibre.customize.ui import load_plugin
ROOT=Path(__file__).resolve().parents[1]; WORK=ROOT/'demo/media-work'; OUT=ROOT/'docs/media'
assert Path(os.environ['CALIBRE_CONFIG_DIRECTORY']).resolve()==(WORK/'config').resolve()
app=Application([])
app.setStyle('Fusion')
app.setFont(QFont('Arial',12))
brand=runpy.run_path(str(ROOT/'plugin/branding.py'))
load_plugin(str(ROOT/'dist'/('JEVBookTags-'+'.'.join(map(str,brand['VERSION']))+'.zip')))
from calibre_plugins.jev_catalog.dialog import CatalogDialog
from calibre_plugins.jev_catalog.config import ConfigWidget
from calibre_plugins.jev_catalog.action import JevCatalogAction
from calibre_plugins.jev_catalog.branding import icon
from calibre_plugins.jev_catalog.settings import save_settings,global_prefs
from calibre_plugins.jev_catalog.dialog import book_metadata
from calibre.gui2.metadata.single import MetadataSingleDialog

class Model(QStandardItemModel):
    def refresh_ids(self,ids): pass
class Tags:
    def recount(self): pass
class Gui(QMainWindow):
    def __init__(self,library):
        super().__init__();self.current_db=library
        self.library_view=QTableView(self);self.library_view.setModel(Model(self));self.tags_view=Tags()
legacy=LibraryDatabase(str(WORK/'library'));db=legacy.new_api;gui=Gui(legacy)
raw=json.loads((WORK/'current-results.json').read_text())
settings=json.loads((WORK/'current-settings.json').read_text())
save_settings(settings,db)
global_prefs['developer_mode']=False
byid={r['book_id']:r for r in raw}
def book_id(title):
    return next(r['book_id'] for r in raw if r['title']==title)
progit=book_id('Pro Git'); linux=book_id('The Linux Command Line')
ids=[progit,linux,book_id('The Hound of the Baskervilles'),book_id('The Time Machine'),
     next(r['book_id'] for r in raw if r['title'].startswith('On the Origin of Species')),
     book_id('Up from Slavery: An Autobiography'),book_id("Alice's Adventures in Wonderland"),book_id('Dracula')]
# Reset only the private media copy to its recorded initial tag state.
db.set_field('tags',{r['book_id']:r['previous_tags'] for r in raw})
# Explicit demonstration fixture; manual tag is excluded from the JEV input.
db.set_field('tags',{progit:['Demo collection']})
byid[progit]['previous_tags']=['Demo collection']
for r in byid.values(): r.pop('applied',None)

def capture(widget,name):
    widget.show();app.processEvents();app.processEvents()
    widget.grab().save(str(OUT/name));return widget.grab().toImage()

config_dialog=QDialog(gui);config_dialog.setWindowTitle('JEV Book Tags — Settings')
config_dialog.resize(1260,870);layout=QVBoxLayout(config_dialog)
config=ConfigWidget(db,config_dialog);layout.addWidget(config)
config.key.clear();config.key.setPlaceholderText('API key hidden for the public demo')
config.table.setColumnWidth(1,200);config.table.setColumnWidth(2,700)
settings_image=capture(config_dialog,'settings.png')
config.advanced_toggle.setChecked(True)
programming_row=next(i for i,c in enumerate(settings['categories']) if c['name']=='Programming')
config.table.setColumnWidth(3,180)
config.table.setColumnWidth(2,650)
config.table.setCurrentCell(programming_row,3)
config.table.scrollToItem(config.table.item(programming_row,3))
config.table.item(programming_row,3).setText('')
threshold_before_image=capture(config_dialog,'category-threshold-before.png')
config.table.item(programming_row,3).setText('0.95')
threshold_image=capture(config_dialog,'category-threshold.png')
row_rect=config.table.visualItemRect(config.table.item(programming_row,3))
row_origin=config.table.viewport().mapTo(config_dialog,QPoint(0,row_rect.y()))
threshold_row=threshold_image.copy(20,row_origin.y(),config_dialog.width()-40,row_rect.height())
config_dialog.hide()

single=CatalogDialog(gui,[progit]);single.resize(1080,720)
single_result=copy.deepcopy(byid[progit]);single_result['metadata']=book_metadata(db,progit)
single.add_result(single_result);single.finished_work()
single_image=capture(single,'single-book-tags.png');single.hide()
preview=CatalogDialog(gui,sorted(byid));preview.resize(1400,780)
for ident in sorted(byid):
    result=copy.deepcopy(byid[ident]);result['metadata']=book_metadata(db,ident)
    preview.add_result(result)
preview.finished_work()
preview_image=capture(preview,'review-results.png')
preview.filter.setCurrentIndex(preview.filter.findData('review'))
review_image=capture(preview,'review-filter.png')
review_result=next(r for r in preview.results if r['status']=='review')
detail=preview.make_details(review_result['book_id'])
detail_image=capture(detail,'review-detail.png');detail.hide()
preview.filter.setCurrentIndex(preview.filter.findData('all'))
preview.select_visible_ready();preview.apply_checked()
applied_image=capture(preview,'apply-results.png');preview.hide()
assert 'Demo collection' in db.field_for('tags',progit)
assert 'Computing' in db.field_for('tags',progit) and 'Programming' in db.field_for('tags',progit)
assert all(db.field_for('tags',r['book_id']) for r in raw if r['status']=='ready')
assert all(not db.field_for('tags',r['book_id']) for r in raw if r['status']!='ready')

action=JevCatalogAction(gui,None);action.qaction=QAction(gui);action.genesis()
editor=MetadataSingleDialog(legacy,gui)
editor.id_list=[progit];editor.current_row=0;editor.set_current_callback=None
editor(progit);editor.resize(1050,830)
editor_image=capture(editor,'metadata-editor.png');editor.hide();action.shutting_down()

report=json.loads((OUT/'real-results.json').read_text())
ready=sum(r['status']=='ready' for r in report['results'])
review=sum(r['status']=='review' for r in report['results'])
tokens=sum(r['tokens_billed'] for r in report['results'])

WIDTH,HEIGHT=1600,900
BG=QColor('#101c2c');INK=QColor('#f4f7fb');MUTED=QColor('#b3c1d0');ACCENT=QColor('#55dfc0')

def text(p,x,y,w,h,content,size=24,color=INK,bold=False):
    f=QFont('Arial',size);f.setBold(bold);p.setFont(f);p.setPen(color)
    p.drawText(QRect(x,y,w,h),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop|Qt.TextFlag.TextWordWrap,content)

def card(filename,kicker,title,body,image=None,footer='',hero=False):
    canvas=QImage(WIDTH,HEIGHT,QImage.Format.Format_RGB32);canvas.fill(BG)
    painter=QPainter(canvas);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(ACCENT);painter.drawRoundedRect(70,62,8,74,4,4)
    text(painter,100,54,1400,38,kicker.upper(),17,ACCENT,True)
    text(painter,100,94,1400,82,title,38,INK,True)
    text(painter,100,176,1400,90,body,22,MUTED)
    if image is not None:
        scaled=image.scaled(QSize(1400,552),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        painter.drawImage((WIDTH-scaled.width())//2,274,scaled)
    elif hero:
        painter.drawPixmap(110,330,210,210,icon().pixmap(210,210))
        text(painter,365,338,1130,210,'One book. A selection. Your entire library.\nConfigurable categories. Review before applying.',34,INK,True)
        text(painter,110,620,1330,120,'Metadata first • Optional EPUB excerpts • Existing tags preserved',25,ACCENT)
    text(painter,100,845,1420,40,footer or 'JEV Book Tags • calibre plugin • Real JEV results • Edited walkthrough',16,MUTED)
    painter.end();canvas.save(str(OUT/filename))

card('01-intro.png','JEV Book Tags','Give your books useful subject tags',
     'A calibre plugin powered by TypeSafe AI JEV. Keep control of the vocabulary and the final tags.',hero=True)
card('02-settings.png','1 / Configure','Choose the categories that matter to you',
     'Start with your API key and categories. Technical tools stay hidden unless developer mode is enabled.',settings_image)
card('03-review.png','2 / Review','Batch tagging with a clear review list',
     f'{ready} of 32 books are ready under the current rules. The review-required book stays unchecked.',preview_image)
card('04-apply.png','3 / Apply','Preserve the tags you already have',
     f'Apply {ready} ready books together. Pro Git keeps its manual Demo collection tag.',applied_image)
card('05-editor.png','4 / Edit a single book','Classify from the metadata editor',
     'The icon beside Tags opens classification using the current form. OK saves staged tags; Cancel discards them.',editor_image)
card('06-results.png','Recorded results','32 books evaluated by the real JEV API',
     f'Model: {report["model"]} • 18 categories • Threshold: 0.85 • Multiple tags • Automatic input',hero=False)
# Add auditable run facts without presenting an accuracy benchmark.
p=OUT/'06-results.png';canvas=QImage(str(p));painter=QPainter(canvas)
text(painter,110,320,1350,85,f'{ready} ready    /    {review} to review    /    0 request errors',39,ACCENT,True)
text(painter,110,435,1370,225,
     '\n'.join(byid[i]['title'] + ' → ' + ', '.join(byid[i]['tags']) for i in [progit,linux,book_id('The Time Machine')]) + '\nOne book remains below the assignment threshold.',28,INK)
text(painter,110,718,1370,95,f'Genuine cached API responses; zero new API calls. Full results are included as JSON and CSV.\nThese are classification suggestions, not a measured accuracy score.',21,MUTED)
painter.end();canvas.save(str(p))
card('07-outro.png','Explore your library','Start with a selection. Review. Then apply.',
     'Use the plugin menu for one book, selected books or the entire current library. Export CSV results and restore the last application when eligible.',hero=True,
     footer='JEV Book Tags • calibre 9+ • API key required • English + Italian interface')
card('banner.png','JEV Book Tags','AI-assisted book tagging for calibre',
     'Your categories. Real probabilities. Reviewable suggestions. Existing tags preserved.',hero=True,
     footer='Powered by TypeSafe AI JEV • No API key or book text included in the public results')
# Readable result table, derived only from the unmodified recorded response.
canvas=QImage(WIDTH,HEIGHT,QImage.Format.Format_RGB32);canvas.fill(BG);painter=QPainter(canvas)
text(painter,100,55,1400,45,'REAL API RESULTS / SELECTED EXAMPLES',17,ACCENT,True)
text(painter,100,105,1400,75,'What JEV actually suggested',38,INK,True)
text(painter,100,185,1400,60,'Independent category scores. Each assigned tag must reach its threshold; sufficient evidence is required.',21,MUTED)
cols=[100,570,1070,1270];headers=['BOOK','SUGGESTED TAGS','TOP SCORE','DECISION']
for x,label in zip(cols,headers):text(painter,x,285,450,40,label,17,ACCENT,True)
examples=[progit,linux,book_id('The Time Machine'),book_id('The Hound of the Baskervilles'),book_id("Alice's Adventures in Wonderland")]
for index,ident in enumerate(examples):
    r=byid[ident]; y=350+index*85
    probs=r['evaluation']['probabilities']; top=max(probs['cat_'+c['id']] for c in report['categories'])
    values=[r['title'],', '.join(r['tags']),f'{top:.2f}', 'Ready' if r['status']=='ready' else 'Review']
    for col,(x,value) in enumerate(zip(cols,values)):
        text(painter,x,y,([435,465,180,210][col]),76,value,22,INK,col==0)
text(painter,100,830,1400,50,'Full 32-book results included • Model returned by the API: jev-1.13.0 • No accuracy benchmark claimed',17,MUTED)
painter.end();canvas.save(str(OUT/'08-examples.png'))
legacy.close()
card('09-threshold-before.png','Advanced options','Empty means: use the global threshold',
     'Open Advanced options and find Programming. An empty category threshold inherits 0.85 (85%).',threshold_before_image)
card('09-threshold.png','Advanced options','One category, its own threshold',
     'Programming: 0.95 (95%). Other categories inherit 0.85 (85%). Pro Git scores 98% for Programming.',threshold_image)
for filename,row in [('09-threshold.png',threshold_row),('09-threshold-before.png',threshold_before_image.copy(20,row_origin.y(),config_dialog.width()-40,row_rect.height()))]:
    canvas=QImage(str(OUT/filename)); painter=QPainter(canvas)
    zoom=row.scaled(QSize(1400,80),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
    painter.drawImage((WIDTH-zoom.width())//2,HEIGHT-120,zoom)
    painter.end();canvas.save(str(OUT/filename))
card('10-single.png','Single book','Choose tags with a click',
     'Suggested tags are selected. Click alternatives to change your choice; confirm to apply.',single_image)
card('11-review-detail.png','Review only what needs attention','A clear reason and selectable alternatives',
     'Dr. Jekyll and Mr. Hyde stays below threshold. No tag is applied without explicit confirmation.',detail_image)
print('Rendered native plugin dialogs and updated explainer cards. Verified manual tag preservation.')
