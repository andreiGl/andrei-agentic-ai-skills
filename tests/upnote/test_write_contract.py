"""MCP contract tests against a fake app, including cross-process failure modes."""
from pathlib import Path
import ast,asyncio,hashlib,json,os,sqlite3,sys,tempfile,unittest
from contextlib import AsyncExitStack
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from fake_app_server import load_server

SERVER=Path(os.environ.get('UPNOTE_TEST_SERVER', str(Path(__file__).resolve().parents[2]/'mcp-servers/upnote-mcp/server.py'))).resolve()
_DEFAULT_OUT=tempfile.TemporaryDirectory(prefix='upnote-mcp-tests-')
BASE=Path(os.environ.get('UPNOTE_TEST_OUT', str(Path(_DEFAULT_OUT.name)/'upnote-write-validation'))).resolve();BASE.mkdir(parents=True,exist_ok=True)
WRAPPER=Path(__file__).with_name('fake_app_server.py')

def async_test(fn):
    def execute(self):
        async def run():
            async with AsyncExitStack() as stack:
                self.stack=stack
                await fn(self)
        asyncio.run(run())
    return execute

class Contract(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='case-',dir=BASE));self.db=self.root/'synthetic-write.sqlite3'
        (self.root/'fixture-guard.json').write_text(json.dumps({'database':str(self.db)}));(self.root/'config.json').write_text('{"dataVersion":17}')
        for node in ast.parse(SERVER.read_text()).body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REQUIRED_COLUMNS' for t in node.targets):schema=ast.literal_eval(node.value)
        with sqlite3.connect(self.db) as c:
            for table,cols in schema.items():c.execute('CREATE TABLE "'+table+'" ('+','.join('"'+col+'"' for col in cols)+')')
            c.execute('CREATE UNIQUE INDEX fixture_lists ON lists(id)');c.execute('CREATE TABLE fake_events(kind,url)');c.execute('CREATE TABLE fake_control(name,value)');c.execute("INSERT INTO fake_control VALUES ('release',0)")
            for nid,title in [('nb-a','Fixture A'),('nb-b','Fixture B')]:
                c.execute('INSERT INTO notebooks(id,title,parent,deleted) VALUES (?,?,NULL,0)',(nid,title));c.execute('INSERT INTO lists(id,content) VALUES (?,?)',('notebooks_'+nid,'[]'))
        self.srv=load_server(SERVER,self.db)
    async def client(self,mode='normal'):
        env={'UPNOTE_DB':str(self.db),'UPNOTE_FAKE_MODE':mode,'PYTHONDONTWRITEBYTECODE':'1'}
        rd,wr=await self.stack.enter_async_context(stdio_client(StdioServerParameters(command=sys.executable,args=[str(WRAPPER),'--server',str(SERVER),'--database',str(self.db)],env=env)))
        session=await self.stack.enter_async_context(ClientSession(rd,wr));await session.initialize();return session
    async def call(self,s,name,**args):
        r=await s.call_tool(name,args);d=r.structured_content or {};text=' '.join(getattr(c,'text','') for c in r.content);return r.is_error,d,text
    async def create(self,s,title='Disposable fixture'):
        err,d,text=await self.call(s,'create_note',title=title,text='<h3>Details</h3><div>Initial content.</div><h3>Other</h3><div>Retain this content.</div>',tags=['fixture-tag'],notebook='nb-a',markdown=False)
        self.assertFalse(err,text);self.assertTrue(d.get('confirmed'),d);return d['note']['id']
    async def rebuild(self,s,name,**args):
        err,p,text=await self.call(s,name,**args);self.assertFalse(err,text);self.assertEqual(p['stage'],'preview')
        err,d,text=await self.call(s,name,**args,expected_revision=p['revision'],preview_token=p['preview_token'],acknowledge_warnings=True)
        self.assertFalse(err,text);self.assertTrue(d.get('done'),d);return d['new_note']['id']
    def event_count(self,kind):
        with sqlite3.connect(self.db) as c:return c.execute('SELECT count(*) FROM fake_events WHERE kind=?',(kind,)).fetchone()[0]
    @async_test
    async def test_all_eight_functions_normal_path(self):
        s=await self.client();n=await self.create(s)
        n=await self.rebuild(s,'append_to_note',note_id=n,text='Appended synthetic line.')
        n=await self.rebuild(s,'make_section',note_id=n,heading='Details')
        n=await self.rebuild(s,'replace_note',note_id=n,text='<div>Replacement synthetic text.</div>',markdown=False)
        n=await self.rebuild(s,'move_note',note_id=n,notebook='nb-b')
        err,d,text=await self.call(s,'open_in_upnote',note_id=n);self.assertFalse(err,text);self.assertTrue(d['sent'])
        for tool in ['move_note_to_trash','restore_note']:
            err,d,text=await self.call(s,tool,note_id=n);self.assertFalse(err,text);self.assertTrue(d['confirmed'])
        # Opening the containing notebook first clears UpNote's stale selection.
        self.assertEqual(self.event_count('open-ui'),2)
    @async_test
    async def test_preview_and_invalid_apply_have_no_app_effect(self):
        s=await self.client();n=await self.create(s);before=self.event_count('create-request')
        err,p,text=await self.call(s,'replace_note',note_id=n,text='Different content');self.assertFalse(err,text)
        self.assertEqual(self.event_count('create-request'),before)
        err,d,text=await self.call(s,'replace_note',note_id=n,text='Changed after preview',expected_revision=p['revision'],preview_token=p['preview_token'],acknowledge_warnings=True);self.assertTrue(err);self.assertIn('differ from the preview',text)
        err,d,text=await self.call(s,'replace_note',note_id=n,text='Different content',expected_revision=p['revision']+1,preview_token=p['preview_token'],acknowledge_warnings=True);self.assertTrue(err);self.assertIn('changed since the preview',text)
        self.assertEqual(self.event_count('create-request'),before)
    @async_test
    async def test_unaccepted_warning_has_no_app_effect(self):
        s=await self.client();n=await self.create(s)
        with sqlite3.connect(self.db) as c:c.execute('UPDATE notes SET pinned=1 WHERE id=?',(n,))
        err,p,text=await self.call(s,'replace_note',note_id=n,text='Replacement content');self.assertFalse(err,text);self.assertTrue(p['warnings'])
        before=self.event_count('create-request');err,d,text=await self.call(s,'replace_note',note_id=n,text='Replacement content',expected_revision=p['revision'],preview_token=p['preview_token']);self.assertTrue(err);self.assertIn("haven't been accepted",text);self.assertEqual(self.event_count('create-request'),before)
    @async_test
    async def test_same_process_timeout_retry_is_refused(self):
        s=await self.client();n=await self.create(s);pending=await self.client('suppress-create')
        err,p,text=await self.call(pending,'append_to_note',note_id=n,text='Delayed append');self.assertFalse(err,text)
        args=dict(note_id=n,text='Delayed append',expected_revision=p['revision'],preview_token=p['preview_token'],acknowledge_warnings=True)
        err,d,text=await self.call(pending,'append_to_note',**args);self.assertFalse(err,text);self.assertFalse(d['done']);before=self.event_count('create-request')
        err,d,text=await self.call(pending,'append_to_note',**args);self.assertTrue(err);self.assertIn('earlier call',text);self.assertEqual(self.event_count('create-request'),before)
    @async_test
    async def test_cross_process_timeout_retry_is_refused(self):
        s=await self.client();n=await self.create(s);a=await self.client('suppress-create');b=await self.client('suppress-create')
        err,p,text=await self.call(a,'append_to_note',note_id=n,text='Delayed append');self.assertFalse(err,text)
        args=dict(note_id=n,text='Delayed append',expected_revision=p['revision'],preview_token=p['preview_token'],acknowledge_warnings=True)
        before=self.event_count('create-request')
        err,d,text=await self.call(a,'append_to_note',**args);self.assertFalse(err,text);self.assertFalse(d['done'])
        err,d,text=await self.call(b,'append_to_note',**args);self.assertTrue(err);self.assertIn('earlier call',text)
        self.assertEqual(self.event_count('create-request')-before,1)

    @async_test
    async def test_concurrent_process_apply_is_refused_before_dispatch(self):
        s=await self.client();n=await self.create(s);a=await self.client('hold-create');b=await self.client()
        err,p,text=await self.call(a,'append_to_note',note_id=n,text='Concurrent append');self.assertFalse(err,text)
        args=dict(note_id=n,text='Concurrent append',expected_revision=p['revision'],preview_token=p['preview_token'],acknowledge_warnings=True)
        before=self.event_count('create-request');task=asyncio.create_task(self.call(a,'append_to_note',**args))
        try:
            for _ in range(100):
                if self.event_count('create-request')>before:break
                await asyncio.sleep(.02)
            self.assertEqual(self.event_count('create-request'),before+1)
            err,d,text=await self.call(b,'append_to_note',**args);self.assertTrue(err);self.assertIn('Another operation',text)
        finally:
            with sqlite3.connect(self.db) as c:c.execute("UPDATE fake_control SET value=1 WHERE name='release'")
        err,d,text=await task;self.assertFalse(err,text);self.assertTrue(d.get('done'),d)
        self.assertEqual(self.event_count('create-request'),before+1)

    @async_test
    async def test_literal_backslash_warning_uses_new_text(self):
        s=await self.client();n=await self.create(s)
        err,p,text=await self.call(s,'replace_note',note_id=n,text='<pre>first\\nsecond</pre>')
        self.assertFalse(err,text);self.assertTrue(any('literal backslash-n' in w for w in p['warnings']))


    @async_test
    async def test_pending_survives_server_restart(self):
        async with AsyncExitStack() as first:
            self.stack=first;s=await self.client();n=await self.create(s);a=await self.client('suppress-create')
            err,p,text=await self.call(a,'append_to_note',note_id=n,text='Restart append');self.assertFalse(err,text)
            args=dict(note_id=n,text='Restart append',expected_revision=p['revision'],preview_token=p['preview_token'],acknowledge_warnings=True)
            err,d,text=await self.call(a,'append_to_note',**args);self.assertFalse(err,text);self.assertFalse(d['done'])
        before=self.event_count('create-request')
        async with AsyncExitStack() as second:
            self.stack=second;b=await self.client()
            err,d,text=await self.call(b,'append_to_note',**args);self.assertTrue(err);self.assertIn('earlier call',text)
            self.assertEqual(self.event_count('create-request'),before)
        journals=list((self.root/'operation-state').glob('*.json'));self.assertEqual(len(journals),1)
        self.assertEqual(set(json.loads(journals[0].read_text())),{'marker','sent_at'})

    @async_test
    async def test_ambiguous_dispatch_failure_blocks_other_process_retry(self):
        s=await self.client();n=await self.create(s);a=await self.client('raise-after-request');b=await self.client()
        err,p,text=await self.call(a,'append_to_note',note_id=n,text='Ambiguous append');self.assertFalse(err,text)
        args=dict(note_id=n,text='Ambiguous append',expected_revision=p['revision'],preview_token=p['preview_token'],acknowledge_warnings=True)
        err,d,text=await self.call(a,'append_to_note',**args);self.assertTrue(err);self.assertIn('ambiguous',text)
        before=self.event_count('create-request');err,d,text=await self.call(b,'append_to_note',**args);self.assertTrue(err);self.assertIn('earlier call',text);self.assertEqual(self.event_count('create-request'),before)

    @async_test
    async def test_corrupt_pending_journal_refuses_apply(self):
        s=await self.client();n=await self.create(s)
        err,p,text=await self.call(s,'append_to_note',note_id=n,text='Corrupt journal append');self.assertFalse(err,text)
        self.srv._operation_path(n,'.json').write_text('{invalid')
        before=self.event_count('create-request')
        err,d,text=await self.call(s,'append_to_note',note_id=n,text='Corrupt journal append',expected_revision=p['revision'],preview_token=p['preview_token'],acknowledge_warnings=True)
        self.assertTrue(err);self.assertIn('Cannot verify an earlier',text);self.assertEqual(self.event_count('create-request'),before)

    SECTION='<div class="shine-collapsible-section"><div class="shine-section-title-wrapper"><div class="shine-section-title shine-placeholder" data-upnote-placeholder-key="title"><div class="shine-section-title-inner"><h3>Sec</h3></div></div></div><div class="shine-section-content shine-placeholder" data-upnote-placeholder-key="content"><div class="shine-section-content-inner"><div>Body.</div></div></div></div>'
    async def seeded_note(self,s,tail='<div>After.</div>'):
        n=await self.create(s)
        return await self.rebuild(s,'replace_note',note_id=n,text=self.SECTION+tail,markdown=False,server_only=True)
    @async_test
    async def test_structural_flatten_refused_and_original_kept(self):
        s=await self.client();n=await self.seeded_note(s)
        flat=await self.client('flatten-sections')
        err,p,text=await self.call(flat,'append_to_note',note_id=n,text='One more line.');self.assertFalse(err,text)
        self.assertEqual(p['structure']['current']['collapsible_sections'],1,p)
        self.assertEqual(p['structure']['sent']['collapsible_sections'],1,p)
        before=self.event_count('create-request')
        err,d,text=await self.call(flat,'append_to_note',note_id=n,text='One more line.',expected_revision=p['revision'],preview_token=p['preview_token'],acknowledge_warnings=True)
        self.assertFalse(err,text);self.assertFalse(d['done'],d);self.assertIn('dropped collapsible-section markup',text)
        self.assertIn('original_note_id',d);self.assertIn('new_note',d)
        with sqlite3.connect(self.db) as c:
            live=c.execute('SELECT count(*) FROM notes WHERE id=? AND trashed=0',(n,)).fetchone()[0]
        self.assertEqual(live,1,'original must stay live when the gate refuses')
    @async_test
    async def test_structural_intact_apply_trashes_original(self):
        s=await self.client();n=await self.seeded_note(s)
        n2=await self.rebuild(s,'append_to_note',note_id=n,text='Added after the section.')
        with sqlite3.connect(self.db) as c:
            html=c.execute('SELECT html FROM notes WHERE id=?',(n2,)).fetchone()[0]
        self.assertEqual(html.count('shine-collapsible-section'),1,'section must survive a healthy rebuild')
    @async_test
    async def test_preview_carries_structure(self):
        s=await self.client();n=await self.seeded_note(s,'<h3>Other</h3><div>Kept.</div>')
        err,p,text=await self.call(s,'replace_note',note_id=n,text=self.SECTION+'<h3>Other</h3><div>Kept.</div>',markdown=False,server_only=True)
        self.assertFalse(err,text)
        self.assertEqual(p['structure']['current']['collapsible_sections'],1,p)
        self.assertEqual(p['structure']['sent']['collapsible_sections'],1,p)
        self.assertEqual(p['structure']['current']['section_placeholders'],2,p)
        err,p,text=await self.call(s,'make_section',note_id=n,heading='Other')
        self.assertFalse(err,text)
        self.assertEqual(p['structure']['sent']['collapsible_sections'],2,p)
        self.assertEqual(p['structure']['sent']['section_placeholders'],4,p)
    @async_test
    async def test_oversized_body_refused_over_mcp(self):
        s=await self.client();n=await self.seeded_note(s)
        big='x'*(self.srv.MCP_TEXT_LIMIT+1)
        before=self.event_count('create-request')
        for name,args in [('replace_note',dict(note_id=n,text=big)),('append_to_note',dict(note_id=n,text=big))]:
            err,d,text=await self.call(s,name,**args)
            self.assertTrue(err,text);self.assertIn('over the 30000-character MCP tool-input limit',text)
            self.assertIn('server_only',text)
        self.assertEqual(self.event_count('create-request'),before,'no app effect without a size-limit bypass')
        err,p,text=await self.call(s,'replace_note',note_id=n,text=big,server_only=True)
        self.assertFalse(err,text);self.assertEqual(p['stage'],'preview')

if __name__=='__main__':unittest.main(verbosity=2)
