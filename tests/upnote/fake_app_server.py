"""Test-only bridge: original server + simulated app, strictly synthetic SQLite data.

It never runs /usr/bin/open or connects to a real UpNote database. App behavior is
simulated, so successful tests are not proof of UpNote UI/formatting compatibility.
"""
from pathlib import Path
import argparse,html,importlib.util,json,os,re,sqlite3,time,uuid
from urllib.parse import urlsplit,parse_qs
from html.parser import HTMLParser


def load_server(source, db):
    db=Path(db).resolve();guard=db.parent/'fixture-guard.json'
    assert guard.is_file() and json.loads(guard.read_text()).get('database')==str(db), 'Missing explicit synthetic fixture guard'
    assert db.name=='synthetic-write.sqlite3' and 'upnote-write-validation' in db.parts
    os.environ['UPNOTE_DB']=str(db)
    os.environ['UPNOTE_MCP_STATE_DIR']=str(db.parent/'operation-state')
    spec=importlib.util.spec_from_file_location('fixture_upnote',source);srv=importlib.util.module_from_spec(spec);spec.loader.exec_module(srv)
    assert srv.DB_PATH.resolve()==db
    srv.CONFIRM_SECONDS=0.05
    def record(kind,url):
        with sqlite3.connect(db,timeout=10) as c:c.execute('INSERT INTO fake_events(kind,url) VALUES (?,?)',(kind,url))
    def open_link(url,background=True):
        u=urlsplit(url);assert u.scheme=='upnote' and u.netloc=='x-callback-url';q={k:v[0] for k,v in parse_qs(u.query).items()};route=u.path
        if route=='/note/new':
            record('create-request',url)
            mode=os.environ.get('UPNOTE_FAKE_MODE','normal')
            if mode=='suppress-create':return
            if mode=='raise-after-request':raise srv.ToolError('Synthetic ambiguous delivery failure')
            if mode=='hold-create':
                deadline=time.monotonic()+8
                while True:
                    with sqlite3.connect(db) as c:released=c.execute("SELECT value FROM fake_control WHERE name='release'").fetchone()[0]
                    if released:break
                    if time.monotonic()>deadline:raise srv.ToolError('Synthetic hold timed out')
                    time.sleep(.02)
            if mode=='barrier':
                deadline=time.monotonic()+8
                while True:
                    with sqlite3.connect(db) as c:n=c.execute("SELECT count(*) FROM fake_events WHERE kind='create-request'").fetchone()[0]
                    if n>=2:break
                    if time.monotonic()>deadline:raise srv.ToolError('Synthetic barrier timed out')
                    time.sleep(.02)
            body=q.get('text','');title=q.get('title','');nid=uuid.uuid4().hex;tags=[html.unescape(t).lstrip('#') for t in re.findall(r'data-upnote-tag="([^"]+)"',body)]
            class Plain(HTMLParser):
                def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
                def handle_data(self,data):self.parts.append(data)
                def handle_starttag(self,tag,attrs):
                    if tag in ['div','p','h1','h2','h3','h4','li','br','pre']:self.parts.append('\n')
                def handle_endtag(self,tag):
                    if tag in ['div','p','h1','h2','h3','h4','li','pre']:self.parts.append('\n')
            plain=Plain();plain.feed(body)
            text=title+'\n'+'\n'.join(line.strip() for line in ''.join(plain.parts).splitlines() if line.strip());markup='<h2>'+html.escape(title)+'</h2>'+body
            with sqlite3.connect(db,timeout=10) as c:
                columns=srv.REQUIRED_COLUMNS['notes'];note={col:0 for col in columns};note.update(id=nid,title=title,text=text,html=markup,tagLinks=json.dumps(tags),noteLinks='[]',fileIds='[]',revision=1,createdAt=1,updatedAt=1)
                c.execute('INSERT INTO notes ('+','.join('"'+k+'"' for k in note)+') VALUES ('+','.join('?' for k in note)+')',list(note.values()))
                for tag in tags:
                    if not c.execute('SELECT 1 FROM tags WHERE title=?',(tag,)).fetchone():c.execute('INSERT INTO tags(title,deleted) VALUES (?,0)',(tag,))
                if q.get('notebook'):
                    rows=c.execute('SELECT id FROM notebooks WHERE title=? AND deleted=0',(q['notebook'],)).fetchall();assert len(rows)==1
                    lid='notebooks_'+rows[0][0];row=c.execute('SELECT content FROM lists WHERE id=?',(lid,)).fetchone();members=json.loads(row[0]) if row else [];members.append(nid)
                    c.execute('INSERT OR REPLACE INTO lists(id,content) VALUES (?,?)',(lid,json.dumps(members)))
            return
        if route in ['/note/moveToTrash','/note/restore']:
            record('trash' if route.endswith('moveToTrash') else 'restore',url)
            with sqlite3.connect(db,timeout=10) as c:c.execute('UPDATE notes SET trashed=?,revision=revision+1 WHERE id=?',(int(route.endswith('moveToTrash')),q['noteId']))
            return
        if route in ['/openNote','/openNotebook','/tag/view','/view']:
            record('open-ui',url);return
        raise AssertionError('Unsupported fake route '+route)
    srv._open_link=open_link
    return srv

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--server',type=Path,required=True);p.add_argument('--database',type=Path,required=True);a=p.parse_args();load_server(a.server,a.database).server.run()
