"""Desktop workspace for passage alignment, review, revision and trilingual export."""
import copy
import json
import tempfile
import uuid
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QFontDatabase, QFont, QPixmap, QImage, QDesktopServices
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,
    QPushButton,QLabel,QLineEdit,QPlainTextEdit,QComboBox,QSpinBox,QCheckBox,QSplitter,
    QTableWidget,QTableWidgetItem,QAbstractItemView,QTabWidget,QScrollArea,QFileDialog,
    QMessageBox,QDialog,QDialogButtonBox,QListWidget,QToolBar,QProgressBar,QInputDialog)
from app.document.trilingual_project import (new_project,load_project,save_project,revise,
    apply_proposal,split_unit,join_units)
from app.processing.trilingual_worker import TrilingualWorker
from app.gui.styles.theme import STYLE_SHEET
from app.utils.paths import BASE_DIR, get_output_dir

STATES={'unmatched':'Not aligned','matched':'AI matched · review pending','uncertain':'Uncertain match',
        'no_counterpart':'No French counterpart','needs_review':'Needs review','reviewed':'Manually reviewed'}


class PdfViewer(QDialog):
    def __init__(self,path,page=1,parent=None):
        super().__init__(parent)
        import pymupdf
        self.document=pymupdf.open(str(path))
        self.setWindowTitle('PDF source / trilingual preview');self.resize(900,850)
        layout=QVBoxLayout(self);self.number=QSpinBox();self.number.setRange(1,len(self.document))
        layout.addWidget(QLabel(str(path)));layout.addWidget(self.number)
        scroll=QScrollArea();scroll.setWidgetResizable(True);self.image=QLabel();self.image.setAlignment(Qt.AlignCenter)
        scroll.setWidget(self.image);layout.addWidget(scroll,1)
        self.number.valueChanged.connect(self.render);self.number.setValue(min(max(page,1),len(self.document)));self.render()
        self.finished.connect(lambda _:self.document.close())

    def render(self):
        import pymupdf
        pix=self.document[self.number.value()-1].get_pixmap(matrix=pymupdf.Matrix(1.2,1.2),alpha=False)
        image=QImage(pix.samples,pix.width,pix.height,pix.stride,QImage.Format_RGB888).copy()
        self.image.setPixmap(QPixmap.fromImage(image))


class TrilingualWindow(QMainWindow):
    def __init__(self,config_factory,parent=None,project=None,output_dir=None):
        super().__init__(parent)
        self.setWindowTitle('Trilingual Book · French / English / Bangla');self.resize(1450,940)
        self.setStyleSheet(STYLE_SHEET)
        self.config_factory=config_factory;self.project=project or new_project();self.project_path=None
        self.output_dir=Path(output_dir or get_output_dir())/'trilingual'
        self.recovery_path=self.output_dir/('recovery_'+uuid.uuid4().hex+'.json')
        self.index=-1;self.passage_index=-1;self.loading=False;self.dirty=False;self.worker=None;self.preview_temp=None
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(800);self.timer.timeout.connect(self.recover)
        from app.fonts.font_manager import FontManager
        font=FontManager.get_instance().get_font_path('Noto Sans Bengali')
        if font:
            fid=QFontDatabase.addApplicationFont(str(font));families=QFontDatabase.applicationFontFamilies(fid)
            if families:self.setFont(QFont(families[0],10))
        bar=QToolBar('Trilingual project',self);bar.setMovable(False);self.addToolBar(bar)
        self.busy_controls=[]
        for title,callback in [('New project',self.new),('Open project / pilot',self.open),('Open Introduction pilot',self.open_pilot),
                               ('Save',self.save),('Save as…',self.save_as),('Preview trilingual PDF',self.preview),
                               ('Export PDF + HTML',self.export),('Export HTML',self.export_html)]:
            action=bar.addAction(title,callback);self.busy_controls.append(action)
        root=QWidget();self.setCentralWidget(root);layout=QVBoxLayout(root)
        self.title=QLineEdit(self.project['title']);layout.addWidget(self.title)
        self.title.textEdited.connect(self.changed)
        hint=QLabel('English controls the sequence. Review French evidence, English, then Bangla for each unit. Alignment and AI revision are proposals; accept them explicitly. Source pages are references, not output page limits.')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self._review_tab();self._prepare_tab()
        bottom=QHBoxLayout();layout.addLayout(bottom)
        self.progress=QProgressBar();bottom.addWidget(self.progress,1)
        self.cancel=QPushButton('Stop after current step');self.cancel.setEnabled(False);self.cancel.clicked.connect(self.stop);bottom.addWidget(self.cancel)
        self.message=QLabel('Open the completed pilot, or choose sources and prepare a batch. No AI calls occur on opening.');self.message.setWordWrap(True);layout.addWidget(self.message)
        from app.gui.zoom import install_zoom
        install_zoom(self)
        self.refresh()

    def button(self,row,title,callback,busy=True):
        button=QPushButton(title);button.clicked.connect(callback);row.addWidget(button)
        if busy:self.busy_controls.append(button)
        return button

    def _review_tab(self):
        tab=QWidget();layout=QVBoxLayout(tab);self.tabs.addTab(tab,'Aligned reading & editing')
        actions=QHBoxLayout();layout.addLayout(actions)
        self.mode=QComboBox();self.mode.addItems(['Configured OpenAI / Groq','Offline mock (test text only)']);actions.addWidget(self.mode)
        self.button(actions,'Align selected',lambda:self.run_ai('align'))
        self.button(actions,'Translate empty selected',lambda:self.run_ai('translate'))
        self.button(actions,'Retranslate selected',lambda:self.run_ai('retranslate'))
        self.button(actions,'Improve current Bangla',lambda:self.run_ai('refine',current_only=True))
        split=QSplitter();layout.addWidget(split,1)
        left=QWidget();left_layout=QVBoxLayout(left)
        self.filter=QComboBox();self.filter.addItems(['All units','Needs alignment / review','Needs Bangla','Has AI proposal']);left_layout.addWidget(self.filter)
        self.filter.currentIndexChanged.connect(self.filter_rows)
        self.button(left_layout,'Add English paragraph',self.add_english)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['English\nPDF','Alignment','Bangla /\nproposal'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.currentCellChanged.connect(self.select_row)
        left_layout.addWidget(self.table,1);split.addWidget(left)
        right=QWidget();right_layout=QVBoxLayout(right);split.addWidget(right);split.setSizes([400,990])
        self.reference=QLabel('No unit selected');self.reference.setWordWrap(True);right_layout.addWidget(self.reference)
        panels=QSplitter();right_layout.addWidget(panels,3)
        fr=QWidget();fr_layout=QVBoxLayout(fr);fr_layout.addWidget(QLabel('1 · French evidence (editable)'))
        self.passages=QComboBox();self.passages.currentIndexChanged.connect(self.select_passage)
        refrow=QHBoxLayout();refrow.addWidget(QLabel('French PDF page'));self.fr_page=QSpinBox();self.fr_page.setRange(1,100000);self.fr_page.setMaximumWidth(100);refrow.addWidget(self.fr_page)
        self.fr_editor=QPlainTextEdit();fr_layout.addWidget(self.fr_editor,1)
        fr_buttons=QHBoxLayout()
        self.button(fr_buttons,'Add passage',self.add_passage);self.button(fr_buttons,'Remove',self.remove_passage)
        self.button(fr_buttons,'View PDF',lambda:self.view_source('french_pdf',self.fr_page.value()))
        panels.addWidget(fr)
        self.english=QPlainTextEdit();self.bangla=QPlainTextEdit()
        for title,editor in [('2 · English reference (editable correction)',self.english),('3 · Bangla translation (editable)',self.bangla)]:
            panel=QWidget();column=QVBoxLayout(panel);column.addWidget(QLabel(title));column.addWidget(editor,1);panels.addWidget(panel)
        panels.setSizes([350,350,400])
        passage_controls=QHBoxLayout();passage_controls.addWidget(self.passages,1);passage_controls.addLayout(refrow);passage_controls.addLayout(fr_buttons);right_layout.addLayout(passage_controls)
        editrow=QHBoxLayout();right_layout.addLayout(editrow)
        self.button(editrow,'View English PDF',self.view_english)
        self.button(editrow,'Split at English cursor',self.split_current)
        self.button(editrow,'Join next unit',self.join_current)
        self.button(editrow,'Restore revision',self.restore)
        self.excluded=QCheckBox('Exclude from translation / export');editrow.addWidget(self.excluded)
        state=QHBoxLayout();right_layout.addLayout(state)
        state.addWidget(QLabel('Alignment review'));self.status=QComboBox()
        for key,label in STATES.items():self.status.addItem(label,key)
        state.addWidget(self.status)
        self.notes=QPlainTextEdit();self.notes.setPlaceholderText('Alignment notes, OCR problems, differences or editorial decisions');self.notes.setMaximumHeight(75);right_layout.addWidget(self.notes)
        self.instructions=QLineEdit(self.project.get('editorial_instructions',''));self.instructions.setPlaceholderText('Optional instructions for Bangla improvement');right_layout.addWidget(self.instructions)
        self.instructions.textEdited.connect(self.changed)
        self.proposal=QPlainTextEdit();self.proposal.setReadOnly(True);self.proposal.setPlaceholderText('AI proposals appear here, separately from your accepted text.');self.proposal.setMaximumHeight(160);right_layout.addWidget(self.proposal,1)
        proposal_buttons=QHBoxLayout();right_layout.addLayout(proposal_buttons)
        self.accept_button=self.button(proposal_buttons,'Accept current proposal',self.accept)
        self.button(proposal_buttons,'Accept selected proposals',self.accept_selected)
        self.button(proposal_buttons,'Reject proposal',self.reject)
        for editor in (self.fr_editor,self.english,self.bangla,self.notes):editor.textChanged.connect(self.changed)
        self.fr_page.valueChanged.connect(self.changed);self.status.currentTextChanged.connect(self.changed);self.excluded.toggled.connect(self.changed)
        self.locked_editors=[self.fr_editor,self.english,self.bangla,self.notes,self.fr_page,self.status,self.excluded,self.title,self.mode,self.instructions]

    def _prepare_tab(self):
        from app.gui.book_locations import book_locations
        defaults=book_locations()
        scroll=QScrollArea();scroll.setWidgetResizable(True);tab=QWidget();form=QFormLayout(tab);form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        scroll.setWidget(tab);self.tabs.addTab(scroll,'Sources, batches & OCR')
        self.paths={}
        for key,label,value in [('english_pdf','English / reference PDF',self.project.get('english_pdf') or defaults['source']),
                                ('french_pdf','French / original PDF',self.project.get('french_pdf') or defaults['original']),
                                ('tesseract','Tesseract program',self.project.get('ocr_settings',{}).get('tesseract',r'C:\Program Files\Tesseract-OCR\tesseract.exe')),
                                ('tessdata','French OCR language-data folder',self.project.get('ocr_settings',{}).get('tessdata',str(BASE_DIR/'models'/'ocr')))]:
            row=QHBoxLayout();field=QLineEdit(str(value));self.paths[key]=field;row.addWidget(field,1)
            self.button(row,'Browse…',lambda checked=False,k=key:self.browse(k));form.addRow(label,row);self.locked_editors.append(field)
        self.ranges={}
        for language,start,end in [('english',28,37),('french',11,20)]:
            row=QHBoxLayout()
            for suffix,value in [('start',start),('end',end)]:
                spin=QSpinBox();spin.setRange(1,100000);spin.setValue(value);row.addWidget(QLabel('From' if suffix=='start' else 'through'));row.addWidget(spin)
                self.ranges[language+'_'+suffix]=spin;self.locked_editors.append(spin)
            form.addRow(language.title()+' physical PDF pages',row)
        self.first_heading=QLineEdit();self.first_heading.setPlaceholderText('Optional: start after this heading on the first batch (exclude preceding preface)')
        self.locked_editors.append(self.first_heading);form.addRow('English start boundary',self.first_heading)
        self.force_ocr=QCheckBox('Use French OCR even when text is selectable');self.force_ocr.setChecked(True);form.addRow(self.force_ocr);self.locked_editors.append(self.force_ocr)
        note=QLabel('Preparation is local and preserves existing units and corrected OCR. AI alignment uses only prepared French pages inside the French range above. Choose a modest evidence window around the English batch; mismatches remain reviewable. No language models or OCR data are downloaded automatically.')
        note.setWordWrap(True);form.addRow(note)
        row=QHBoxLayout();self.button(row,'Prepare / resume selected batch',self.prepare);self.button(row,'Next English batch',self.next_batch);self.button(row,'Edit prepared source / OCR text',self.edit_ocr);form.addRow(row)
        row=QHBoxLayout();self.button(row,'Apply moved source paths',lambda:self.start('relink',options={k:self.paths[k].text().strip() for k in ('english_pdf','french_pdf')}));self.button(row,'Page extraction report',self.extraction_report);form.addRow(row)

    def current(self):
        return self.project['units'][self.index] if 0<=self.index<len(self.project['units']) else None

    def changed(self,*_):
        if self.loading:return
        # Coalesce typing into one revision instead of storing a whole unit per key.
        if self.current():self.current().pop('proposal',None)
        self.dirty=True;self.timer.start();self.show_proposal()

    def capture(self):
        if self.loading:return
        self.project['title']=self.title.text()
        self.project['editorial_instructions']=self.instructions.text()
        self.project['ocr_settings']={k:self.paths[k].text().strip() for k in ('tesseract','tessdata')}
        unit=self.current()
        if not unit:return
        french=copy.deepcopy(unit['french'])
        if 0<=self.passage_index<len(french):
            french[self.passage_index].update(page=self.fr_page.value(),text=self.fr_editor.toPlainText())
        changes=dict(english=self.english.toPlainText(),bangla=self.bangla.toPlainText(),french=french,
                     alignment_note=self.notes.toPlainText(),excluded=self.excluded.isChecked())
        text_changed=any(unit.get(k)!=changes[k] for k in ('english','french'))
        revise(unit,changes)
        unit['alignment_status']='needs_review' if text_changed else self.status.currentData()
        if text_changed:
            self.loading=True;self.status.setCurrentIndex(self.status.findData('needs_review'));self.loading=False

    def recover(self):
        try:
            self.capture();save_project(self.project,self.recovery_path)
            u=self.current()
            if u and self.index<self.table.rowCount():
                short={'matched':'AI matched','reviewed':'Reviewed','uncertain':'Uncertain','no_counterpart':'No counterpart','needs_review':'Needs review','unmatched':'Not aligned'}
                self.table.item(self.index,1).setText(short.get(u.get('alignment_status'),'Needs review'))
                self.table.item(self.index,2).setText(('Proposal · ' if u.get('proposal') else '')+('Bangla ready' if u['bangla'] else 'Pending')+(' · excluded' if u.get('excluded') else ''))
            self.statusBar().showMessage('Recovery copy saved: '+str(self.recovery_path))
        except Exception:
            self.message.setText('Recovery save failed. Use Save as to choose a writable folder; keep this window open.')

    def refresh(self,keep_id=None):
        self.loading=True
        self.table.setRowCount(len(self.project['units']))
        for row,u in enumerate(self.project['units']):
            short_states={'matched':'AI matched','reviewed':'Reviewed','uncertain':'Uncertain','no_counterpart':'No counterpart','needs_review':'Needs review','unmatched':'Not aligned'}
            values=[', '.join(map(str,u['english_pages'])),short_states.get(u.get('alignment_status'), 'Needs review'),
                    ('Proposal · ' if u.get('proposal') else '')+('Bangla ready' if u['bangla'] else 'Pending')+(' · excluded' if u.get('excluded') else '')]
            for col,value in enumerate(values):self.table.setItem(row,col,QTableWidgetItem(value))
        for col,width in enumerate((90,105,135)):self.table.setColumnWidth(col,width)
        self.table.horizontalScrollBar().setValue(0)
        self.loading=False
        self.filter_rows()
        target=next((i for i,u in enumerate(self.project['units']) if u['id']==keep_id),0)
        self.index=-1
        if self.project['units']:
            self.table.setCurrentCell(target,0);self.load_unit(target)
        else:self.load_unit(-1)

    def filter_rows(self,*_):
        mode=self.filter.currentIndex()
        for i,u in enumerate(self.project['units']):
            show=(mode==0 or mode==1 and u.get('alignment_status') not in ('matched','reviewed') or mode==2 and not u['bangla'] or mode==3 and u.get('proposal'))
            self.table.setRowHidden(i,not bool(show))

    def select_row(self,row,*_):
        if self.loading:return
        self.capture();self.load_unit(row)

    def load_unit(self,row):
        self.loading=True;self.index=row;self.passage_index=-1
        u=self.current();self.passages.clear()
        for editor in (self.fr_editor,self.english,self.bangla,self.notes):editor.clear()
        if u:
            self.reference.setText('English physical PDF page(s): '+', '.join(map(str,u['english_pages']))+' · '+u['id'])
            self.english.setPlainText(u['english']);self.bangla.setPlainText(u['bangla']);self.notes.setPlainText(u.get('alignment_note',''))
            self.status.setCurrentIndex(max(0,self.status.findData(u.get('alignment_status','unmatched'))));self.excluded.setChecked(u.get('excluded',False))
            for i,f in enumerate(u['french']):self.passages.addItem(f'Passage {i+1} · PDF {f["page"]}')
        else:self.reference.setText('No unit selected')
        self.loading=False
        if u and u['french']:self.select_passage(0)
        self.show_proposal()

    def select_passage(self,index):
        if self.loading:return
        self.capture();self.loading=True;self.passage_index=index
        u=self.current();self.fr_editor.clear()
        if u and 0<=index<len(u['french']):
            self.fr_editor.setPlainText(u['french'][index]['text']);self.fr_page.setValue(u['french'][index]['page'])
        self.loading=False

    def show_proposal(self):
        u=self.current();p=u.get('proposal') if u else None
        text=''
        if p:
            if p.get('kind')=='align':
                text='Proposed French alignment · '+STATES.get(p.get('alignment_status'),'Needs review')+'\n\n'
                text+='\n\n'.join(f'French PDF {f["page"]}\n{f["text"]}' for f in p.get('french',[]))
                text+='\n\n'+p.get('alignment_note','')
            else:
                text='Proposed Bangla\n\n'+p.get('bangla','')+'\n\nChanges: '+p.get('reasons','')+'\nUncertainties: '+p.get('ambiguities','')
        self.proposal.setPlainText(text)
        self.proposal.setVisible(bool(p))
        self.accept_button.setEnabled(bool(p) and not (self.worker and self.worker.isRunning()))

    def add_passage(self):
        self.capture();u=self.current()
        if not u:return
        revise(u,{'french':u['french']+[dict(page=self.ranges['french_start'].value(),text='')]},'Added French evidence slot')
        self.dirty=True;self.load_unit(self.index);self.passages.setCurrentIndex(len(u['french'])-1);self.timer.start()

    def remove_passage(self):
        self.capture();u=self.current()
        if not u or not 0<=self.passage_index<len(u['french']):return
        french=copy.deepcopy(u['french']);french.pop(self.passage_index);revise(u,{'french':french},'Removed French passage (retained in history)')
        self.dirty=True;self.load_unit(self.index);self.timer.start()

    def add_english(self):
        self.capture()
        text,ok=QInputDialog.getMultiLineText(self,'Add English paragraph','Enter extracted or corrected English text:')
        if not ok or not text.strip():return
        page,ok=QInputDialog.getInt(self,'English source reference','Physical PDF page:',self.ranges['english_start'].value(),1,100000)
        if not ok:return
        unit=dict(id=uuid.uuid4().hex,english=text,english_pages=[page],french=[],bangla='',status='pending',alignment_status='unmatched',history=[],alignment_note='Manually added English paragraph; check source reference.')
        self.project['units'].insert(self.index+1 if self.current() else len(self.project['units']),unit)
        self.dirty=True;self.refresh(unit['id']);self.recover()

    def accept(self):
        self.capture();u=self.current()
        if not u or not u.get('proposal'):return
        try:apply_proposal(self.project,u,u['proposal']['kind'])
        except ValueError as e:self.warn(str(e));return
        self.dirty=True;self.refresh(u['id']);self.recover()

    def reject(self):
        u=self.current()
        if u and u.get('proposal'):
            revise(u,{'proposal':None},'Rejected AI proposal');u.pop('proposal',None);self.dirty=True;self.show_proposal();self.recover()

    def accept_selected(self):
        self.capture();rows=[i.row() for i in self.table.selectionModel().selectedRows()]
        for row in rows:
            unit=self.project['units'][row]
            if unit.get('proposal'):
                try:apply_proposal(self.project,unit,unit['proposal']['kind'])
                except ValueError as e:self.warn(str(e))
        self.dirty=True;self.refresh(self.current()['id'] if self.current() else None);self.recover()

    def restore(self):
        self.capture();u=self.current()
        if not u or not u.get('history'):self.warn('No prior revision for this unit.');return
        choices=[f'{i+1} · {v["at"]} · {v["reason"]}' for i,v in enumerate(u['history'])]
        item,ok=QInputDialog.getItem(self,'Restore revision','Choose previous unit text',choices,len(choices)-1,False)
        if ok:
            snapshot=copy.deepcopy(u['history'][choices.index(item)]['unit']);snapshot.pop('proposal',None)
            revise(u,snapshot,'Restored revision');u.pop('proposal',None);self.dirty=True;self.refresh(u['id']);self.recover()

    def split_current(self):
        self.capture()
        if not self.current():return
        try:split_unit(self.project,self.index,self.english.textCursor().position())
        except ValueError as e:self.warn(str(e));return
        self.dirty=True;self.refresh();self.recover();self.message.setText('Split complete. Redistribute the retained French and Bangla before marking both units reviewed.')

    def join_current(self):
        self.capture()
        if not self.current():return
        try:join_units(self.project,self.index)
        except ValueError as e:self.warn(str(e));return
        self.dirty=True;self.refresh();self.recover()

    def browse(self,key):
        if key=='tessdata':path=QFileDialog.getExistingDirectory(self,'French OCR data folder',self.paths[key].text())
        else:path,_=QFileDialog.getOpenFileName(self,'Choose '+key.replace('_',' '),self.paths[key].text(),'PDF (*.pdf)' if key.endswith('_pdf') else 'Program (*.exe);;All files (*)')
        if path:self.paths[key].setText(path)

    def view_source(self,key,page):
        try:PdfViewer(self.project.get(key) or self.paths[key].text(),page,self).exec()
        except Exception:self.warn('Source PDF could not be opened. Check its path in Sources, batches & OCR.')

    def view_english(self):
        u=self.current()
        if u and u['english_pages']:self.view_source('english_pdf',u['english_pages'][0])

    def edit_ocr(self):
        pages=self.project['french_pages']
        if not pages:self.warn('Prepare French pages first.');return
        dialog=QDialog(self);dialog.setWindowTitle('French evidence / OCR corrections');dialog.resize(1000,750)
        layout=QVBoxLayout(dialog);picker=QComboBox();picker.addItems([f'French physical PDF {p["physical_page"]}' for p in pages]);layout.addWidget(picker)
        text=QPlainTextEdit();layout.addWidget(text,1)
        hint=QLabel('Correct OCR here, then select a corresponding passage and assign it to the current English unit. Original extraction and correction history are retained.');hint.setWordWrap(True);layout.addWidget(hint)
        current=[0]
        def capture_page():
            p=pages[current[0]];value=text.toPlainText()
            if p['text']!=value:
                p.setdefault('history',[]).append(p['text']);p['text']=value
                for u in self.project['units']:
                    if any(f['page']==p['physical_page'] for f in u['french']):
                        u['alignment_status']='needs_review';u.pop('proposal',None)
                self.dirty=True
        def change(index):capture_page();current[0]=index;text.setPlainText(pages[index]['text'])
        text.setPlainText(pages[0]['text']);picker.currentIndexChanged.connect(change)
        row=QHBoxLayout();layout.addLayout(row)
        def assign():
            capture_page();u=self.current();selection=text.textCursor().selectedText().replace('\u2029','\n')
            if not u or not selection.strip():self.warn('Select French text and an English reading unit first.');return
            revise(u,{'french':u['french']+[dict(page=pages[current[0]]['physical_page'],text=selection)]},'Assigned selected French evidence')
            self.dirty=True;dialog.accept()
        button=QPushButton('Add selected passage to current English unit');button.clicked.connect(assign);row.addWidget(button)
        view=QPushButton('View original French PDF');view.clicked.connect(lambda:self.view_source('french_pdf',pages[current[0]]['physical_page']));row.addWidget(view)
        close=QPushButton('Save corrections & close');close.clicked.connect(dialog.accept);row.addWidget(close)
        dialog.exec();capture_page();self.refresh(self.current()['id'] if self.current() else None);self.recover()

    def next_batch(self):
        pages=[n for u in self.project['units'] for n in u['english_pages']]
        length=self.ranges['english_end'].value()-self.ranges['english_start'].value()+1
        start=max(pages,default=self.ranges['english_end'].value())+1
        self.ranges['english_start'].setValue(start);self.ranges['english_end'].setValue(start+max(1,length)-1);self.first_heading.clear()
        self.message.setText('Next English range selected. Adjust the French evidence range before preparation; page offsets are not assumed.')

    def extraction_report(self):
        dialog=QDialog(self);dialog.setWindowTitle('Page extraction report');dialog.resize(800,600);layout=QVBoxLayout(dialog)
        text=QPlainTextEdit();text.setReadOnly(True);lines=[]
        for language in ('english','french'):
            for page in self.project.get(language+'_pages',[]):
                lines.append(f'{language.title()} PDF {page["physical_page"]}: {len(page.get("text",""))} characters · {page.get("method","imported")}'+(' · NO TEXT: inspect source and add a corrected English unit if needed' if not page.get('text','').strip() else ''))
        text.setPlainText('\n'.join(lines) or 'No prepared-page inventory yet. Imported pilot units retain their original source references.');layout.addWidget(text)
        close=QPushButton('Close');close.clicked.connect(dialog.accept);layout.addWidget(close);dialog.exec()

    def prepare(self):
        self.capture();options={k:f.text().strip() for k,f in self.paths.items()}
        options.update({k:v.value() for k,v in self.ranges.items()})
        if any(options[k+'_start']>options[k+'_end'] for k in ('english','french')):self.warn('Start pages must not exceed end pages.');return
        options.update(first_heading=self.first_heading.text().strip(),force_french_ocr=self.force_ocr.isChecked(),batch_id=uuid.uuid4().hex)
        self.start('prepare',options=options)

    def run_ai(self,action,current_only=False):
        self.capture()
        ids=[self.current()['id']] if current_only and self.current() else [self.project['units'][i.row()]['id'] for i in self.table.selectionModel().selectedRows()]
        if not ids:self.warn('Select one or more English units first.');return
        try:
            config={'mock':True} if self.mode.currentIndex()==1 else self.config_factory()
            config=dict(config,instructions=self.instructions.text(),french_range=(self.ranges['french_start'].value(),self.ranges['french_end'].value()))
        except ValueError as e:self.warn(str(e));return
        if action=='align' and not self.project['french_pages']:self.warn('Prepare French evidence pages before alignment.');return
        self.message.setText('Offline mock selected.' if config.get('mock') else f'Requesting {len(ids)} selected unit(s) using configured cloud credit. Stop retains completed proposals.')
        self.start(action,config=config,ids=ids)

    def start(self,action,**kwargs):
        if self.worker and self.worker.isRunning():return
        self.capture();self.recover();self.worker=TrilingualWorker(self.project,action,parent=self,**kwargs)
        self.worker.updated.connect(self.worker_updated);self.worker.outcome.connect(self.worker_outcome);self.worker.problem.connect(self.warn)
        self.worker.finished.connect(self.worker_finished)
        self.set_busy(True);self.worker.start()

    def worker_updated(self,project,current,total,message):
        self.project=project;self.dirty=True;self.progress.setRange(0,max(1,total));self.progress.setValue(current);self.message.setText(message)
        # Editors are locked for the worker snapshot; do not capture stale widgets here.
        try:save_project(self.project,self.recovery_path)
        except Exception:self.message.setText(message+' Recovery save failed; use Save as when processing stops.')

    def worker_outcome(self,project,message):
        self.project=project;self.dirty=True;self.message.setText(message)

    def worker_finished(self):
        keep=self.current()['id'] if self.current() else None
        self.set_busy(False);self.refresh(keep);self.recover()
        if self.preview_temp:
            path=Path(self.preview_temp.name)/'preview.pdf'
            if path.exists():PdfViewer(path,parent=self).exec()
            self.preview_temp.cleanup();self.preview_temp=None

    def set_busy(self,busy):
        self.timer.stop()
        for control in self.busy_controls+self.locked_editors+[self.table,self.passages,self.filter]:control.setEnabled(not busy)
        self.cancel.setEnabled(busy);self.accept_button.setEnabled(not busy and bool(self.current() and self.current().get('proposal')))

    def stop(self):
        if self.worker:self.worker.requestInterruption();self.message.setText('Stopping after the current extraction or bounded network request (up to two minutes). Completed work is retained.')

    def export(self,html_only=False):
        self.capture()
        if not self.project['units']:self.warn('Open a pilot/project or prepare reading units first.');return
        extension='html' if html_only else 'pdf'
        path,_=QFileDialog.getSaveFileName(self,'Export trilingual '+('HTML reading copy' if html_only else 'PDF and HTML reading copy'),str(self.output_dir/f'reading.{extension}'),f'{extension.upper()} (*.{extension})')
        if path:
            target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
            self.start('export',options=dict(path=str(target),html_only=html_only))

    def export_html(self):self.export(True)

    def preview(self):
        if not self.project['units']:self.warn('Open a pilot/project or prepare reading units first.');return
        self.preview_temp=tempfile.TemporaryDirectory(prefix='trilingual_preview_')
        self.start('export',options=dict(path=str(Path(self.preview_temp.name)/'preview.pdf')))

    def warn(self,message):
        self.message.setText(message);QMessageBox.warning(self,'Trilingual Book',message)

    def can_leave(self):
        if self.worker and self.worker.isRunning():self.warn('Stop processing and wait for the current step before closing or opening another project.');return False
        if not self.dirty:return True
        answer=QMessageBox.question(self,'Save editable work?','Save this project before continuing? A recovery copy is also retained.',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
        if answer==QMessageBox.Cancel:return False
        if answer==QMessageBox.Save:return self.save()
        return True

    def new(self):
        if not self.can_leave():return
        self.timer.stop();self.project=new_project();self.project_path=None;self.dirty=False
        self.recovery_path=self.output_dir/('recovery_'+uuid.uuid4().hex+'.json');self.title.setText(self.project['title']);self.instructions.clear();self.refresh()

    def open(self):
        path,_=QFileDialog.getOpenFileName(self,'Open trilingual project, pilot, or recovery',str(self.output_dir.parent),'Trilingual JSON (*.json)')
        if path:self.open_path(path)

    def open_pilot(self):
        candidates=[self.output_dir.parent/'trilingual_intro_20261120'/'pilot.json',BASE_DIR/'output'/'trilingual_intro_20261120'/'pilot.json']
        path=next((p for p in candidates if p.is_file()),None)
        if path:self.open_path(path)
        else:self.open()

    def open_path(self,path):
        if not self.can_leave():return
        try:project=load_project(path)
        except Exception as e:self.warn(str(e));return
        self.timer.stop();self.project=project
        # Imported pilots are read-only inputs: first Save always asks for a new native project.
        pilot_import=json.loads(Path(path).read_text(encoding='utf-8')).get('format')!='trilingual-book-v1'
        self.project_path=None if pilot_import else str(path)
        self.recovery_path=self.output_dir/('recovery_'+uuid.uuid4().hex+'.json')
        self.dirty=pilot_import;self.title.setText(project['title']);self.instructions.setText(project.get('editorial_instructions',''))
        for key in ('english_pdf','french_pdf'):self.paths[key].setText(project.get(key,''))
        for key,value in project.get('ocr_settings',{}).items():
            if key in ('tesseract','tessdata'):self.paths[key].setText(value)
        pages=[n for u in project['units'] for n in u['english_pages']]
        if pages:self.ranges['english_start'].setValue(min(pages));self.ranges['english_end'].setValue(max(pages))
        french=[p['physical_page'] for p in project['french_pages']]
        if french:self.ranges['french_start'].setValue(min(french));self.ranges['french_end'].setValue(max(french))
        if project.get('batches'):
            latest=project['batches'][-1]
            for key,spin in self.ranges.items():
                if key in latest:spin.setValue(latest[key])
        self.refresh();self.message.setText(f'Loaded {len(project["units"])} reading units offline. Save as an editable project to keep future work.');self.recover()

    def save(self):
        if not self.project_path:return self.save_as()
        self.capture()
        try:save_project(self.project,self.project_path)
        except Exception as e:self.warn(str(e));return False
        self.dirty=False;self.message.setText('Project saved: '+str(self.project_path));return True

    def save_as(self):
        path,_=QFileDialog.getSaveFileName(self,'Save editable trilingual project',str(self.output_dir/'book_project.json'),'Trilingual project (*.json)')
        if not path:return False
        if self.project.get('imported_from') and Path(path).resolve()==Path(self.project['imported_from']).resolve():
            self.warn('Choose a new project filename to preserve the original pilot.');return False
        previous=self.project_path;self.project_path=path
        if self.save():return True
        self.project_path=previous;return False

    def closeEvent(self,event):
        if self.can_leave():self.timer.stop();event.accept()
        else:event.ignore()
