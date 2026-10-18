from browser_support import start,stop,PASSWORD
from playwright.sync_api import sync_playwright
import json
r=start(8882)
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(headless=True,args=['--no-sandbox']);p=b.new_page(viewport={'width':1500,'height':1050});errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
  p.goto(r[3]);p.locator('[name=username]').fill('admin');p.locator('[name=password]').fill(PASSWORD);p.locator('#login button').click();p.locator('.sidebar [data-page=map]').click()
  original=p.locator('.zone').count();assert original==4
  p.locator('[data-act=warehouse-edit]').first.click();p.locator('#name').fill('본창고');p.locator('[data-act=save-warehouse]').click();p.locator('#modal').wait_for(state='hidden')
  p.locator('[data-act=warehouse-edit]').nth(1).click();p.locator('#name').fill('작은 창고');p.locator('#shape').select_option('L');p.locator('[data-act=save-warehouse]').click();p.locator('#modal').wait_for(state='hidden');assert p.locator('.zone').count()==0
  p.locator('[data-act=edit-map]').click();p.locator('[data-act=zone]').click();p.locator('#name').fill('보관 30대');p.locator('#rows').fill('3');p.locator('#cols').fill('10');p.locator('[data-act=save-zone]').click();p.locator('#modal').wait_for(state='hidden');assert p.locator('.slot').count()==30
  small=p.locator('#warehouse-select').input_value();p.locator('#warehouse-select').select_option('main');assert p.locator('.zone').count()==4
  p.locator('#warehouse-select').select_option(small);p.reload();p.locator('.sidebar [data-page=map]').click();assert p.locator('#warehouse-select').input_value()==small and p.locator('.slot').count()==30
  p.locator('[data-act=warehouse-edit]').first.click();p.locator('#width').fill('300');p.locator('[data-act=save-warehouse]').click();p.locator('.modal-error').wait_for();assert '외곽 밖' in p.locator('.modal-error').inner_text();p.locator('[data-act=close]').click()
  p.locator('[data-act=warehouse-edit]').first.click();p.locator('#warehouse-active').uncheck();p.on('dialog',lambda d:d.accept());p.locator('[data-act=save-warehouse]').click();p.locator('#modal').wait_for(state='hidden');assert p.locator('#warehouse-select option').count()==1
  p.locator('[data-act=warehouse-list]').click();p.locator('[data-act=warehouse-edit]').filter(has_text='설정').last.click();p.locator('#warehouse-active').check();p.locator('[data-act=save-warehouse]').click();p.locator('#modal').wait_for(state='hidden');assert p.locator('.slot').count()==30
  assert not errors,errors
  print(json.dumps({'rename':True,'create_L_shape':True,'thirty_slots':True,'warehouse_isolation':True,'reload':True,'shrink_blocked':True,'deactivate_reactivate':True,'js_errors':errors}))
  b.close()
finally:stop(r)
