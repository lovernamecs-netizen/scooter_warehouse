from browser_support import start,stop,PASSWORD
from playwright.sync_api import sync_playwright
import json
runtime=start(8881)
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,args=['--no-sandbox']);p=browser.new_page(viewport={'width':412,'height':915},is_mobile=True,has_touch=True);errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
  p.goto(runtime[3]);p.locator('[name=username]').fill('admin');p.locator('[name=password]').fill(PASSWORD);p.locator('#login button').click();p.locator('.bottom-nav [data-page=map]').click();assert p.locator('meta[name=theme-color]').get_attribute('content')=='#f4f7f8'
  target=p.locator('.slot').first;sid=target.get_attribute('data-slot')
  target.tap();p.locator('[data-act=map-register]').tap();p.locator('#model_id').select_option(label='PCX125');p.locator('#color_id').select_option(label='화이트');p.locator('[data-act=save-receipt]').click();p.locator('[data-act=vehicle-edit]').wait_for()
  assert 'VIN 미등록' in p.locator('#modal').inner_text()
  vid=p.locator('#modal').get_attribute('data-vehicle')
  p.locator('[data-act=close]').click();slot=p.locator(f'.slot[data-slot="{sid}"]');assert slot.get_attribute('data-vehicle')==vid
  destination=p.locator('.slot').nth(1);dest=destination.get_attribute('data-slot');destination.tap();p.locator('[data-act=map-place]').tap();p.locator('#map-vehicle-list button').first.click();p.locator('[data-act=save-move]').click();p.locator('#modal').wait_for(state='hidden')
  p.locator(f'.slot[data-slot="{dest}"]').click();p.locator('[data-act=vehicle-edit]').click();p.locator('#vin').fill('L1234567890123456');p.set_viewport_size({'width':884,'height':1000});assert p.locator('#vin').input_value()=='L1234567890123456';p.locator('[data-act=save-vehicle]').click()
  p.locator('[data-act=delete-vehicle]').click();p.locator('#reason').fill('오입력 테스트');p.locator('#confirmation').fill('삭제');p.locator('[data-act=save-delete]').click();p.locator('#modal').wait_for(state='hidden')
  assert p.locator(f'.slot[data-slot="{dest}"]').get_attribute('data-vehicle')==''
  assert not errors,errors
  print(json.dumps({'mobile_touch_receipt':True,'fold_input_preserved':True,'light_theme_metadata':True,'existing_vehicle_move_menu':True,'later_vin':True,'delete_clears_slot':True,'js_errors':errors}))
  browser.close()
finally:stop(runtime)
