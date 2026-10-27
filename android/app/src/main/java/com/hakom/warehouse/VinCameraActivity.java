package com.hakom.warehouse;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.graphics.*;
import android.os.Bundle;
import android.view.*;
import android.widget.*;
import androidx.activity.ComponentActivity;
import androidx.camera.core.*;
import androidx.camera.lifecycle.ProcessCameraProvider;
import androidx.camera.view.PreviewView;
import androidx.core.content.ContextCompat;
import androidx.exifinterface.media.ExifInterface;
import java.io.*;
import java.util.concurrent.*;

/** Private rear-camera screen. Crop coordinates use the displayed image, not screen pixels. */
public class VinCameraActivity extends ComponentActivity {
    PreviewView preview; ImageCapture capture; androidx.camera.core.Camera camera;
    ProcessCameraProvider provider; Bitmap bitmap; CropView crop;
    TextView message; ImageButton shutter; File shot; boolean shooting=false,torch=false,closed=false,cropping=false;
    final ExecutorService io=Executors.newSingleThreadExecutor();
    @Override public void onCreate(Bundle state){super.onCreate(state);getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        if(state!=null){String saved=state.getString("shot");if(saved!=null&&new File(saved).exists()){shot=new File(saved);try{showCrop();return;}catch(Exception ignored){}}}
        cameraScreen();if(ContextCompat.checkSelfPermission(this,Manifest.permission.CAMERA)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.CAMERA},40);else bindCamera();
    }
    LinearLayout root(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);l.setBackgroundColor(Color.rgb(244,247,248));int pad=(int)(12*getResources().getDisplayMetrics().density);l.setPadding(pad,pad,pad,pad);SafeArea.setContent(this,l);return l;}
    TextView text(LinearLayout l,String value){TextView t=new TextView(this);t.setText(value);t.setTextSize(16);t.setTextColor(Color.BLACK);t.setPadding(0,8,0,8);l.addView(t);return t;}
    Button button(LinearLayout row,String label,Runnable run){Button b=new Button(this);b.setText(label);row.addView(b,new LinearLayout.LayoutParams(0,ViewGroup.LayoutParams.WRAP_CONTENT,1));b.setOnClickListener(v->run.run());return b;}
    void cameraScreen(){cropping=false;LinearLayout l=root();message=text(l,"후면 카메라 · VIN 17자리 줄을 크게 촬영하세요.\n글자를 터치하면 초점을 맞춥니다. 촬영 후 인식 영역을 선택합니다.");
        preview=new PreviewView(this);preview.setImplementationMode(PreviewView.ImplementationMode.COMPATIBLE);preview.setScaleType(PreviewView.ScaleType.FIT_CENTER);l.addView(preview,new LinearLayout.LayoutParams(-1,0,1));
        preview.setOnTouchListener((v,event)->{if(event.getAction()==MotionEvent.ACTION_UP&&camera!=null){camera.getCameraControl().startFocusAndMetering(new FocusMeteringAction.Builder(preview.getMeteringPointFactory().createPoint(event.getX(),event.getY())).setAutoCancelDuration(3,TimeUnit.SECONDS).build());v.performClick();}return true;});
        SeekBar zoom=new SeekBar(this);zoom.setMax(100);l.addView(zoom);zoom.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onStartTrackingTouch(SeekBar s){}public void onStopTrackingTouch(SeekBar s){}public void onProgressChanged(SeekBar s,int value,boolean user){if(camera!=null&&user){ZoomState z=camera.getCameraInfo().getZoomState().getValue();if(z!=null)camera.getCameraControl().setZoomRatio(Math.max(z.getMinZoomRatio(),1f+(Math.min(z.getMaxZoomRatio(),4f)-1f)*value/100f));}}});
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);l.addView(row,new LinearLayout.LayoutParams(-1,-2));
        button(row,"취소",this::onBackPressed);
        LinearLayout center=new LinearLayout(this);center.setOrientation(LinearLayout.VERTICAL);center.setGravity(Gravity.CENTER);row.addView(center,new LinearLayout.LayoutParams(0,-2,1));
        shutter=new ImageButton(this);shutter.setImageResource(R.drawable.ic_camera_capture);shutter.setContentDescription("VIN 사진 촬영");
        android.graphics.drawable.GradientDrawable bg=new android.graphics.drawable.GradientDrawable();bg.setShape(android.graphics.drawable.GradientDrawable.OVAL);bg.setColor(Color.rgb(0,125,121));bg.setStroke(dp(3),Color.WHITE);shutter.setBackground(bg);shutter.setPadding(dp(16),dp(16),dp(16),dp(16));
        center.addView(shutter,new LinearLayout.LayoutParams(dp(72),dp(72)));shutter.setOnClickListener(v->take());shutter.setEnabled(false);
        TextView caption=text(center,"촬영");caption.setGravity(Gravity.CENTER);caption.setTextSize(13);
        button(row,"조명",()->{if(camera!=null&&camera.getCameraInfo().hasFlashUnit()){torch=!torch;camera.getCameraControl().enableTorch(torch);}else Toast.makeText(this,"조명을 지원하지 않는 카메라입니다.",Toast.LENGTH_SHORT).show();});

    }
    int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
    void bindCamera(){var future=ProcessCameraProvider.getInstance(this);future.addListener(()->{if(closed||cropping)return;try{provider=future.get();if(!provider.hasCamera(CameraSelector.DEFAULT_BACK_CAMERA))throw new IllegalStateException("후면 카메라가 없습니다.");provider.unbindAll();Preview p=new Preview.Builder().build();p.setSurfaceProvider(preview.getSurfaceProvider());capture=new ImageCapture.Builder().setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY).setTargetRotation(getWindowManager().getDefaultDisplay().getRotation()).build();camera=provider.bindToLifecycle(this,CameraSelector.DEFAULT_BACK_CAMERA,p,capture);torch=false;shutter.setEnabled(true);}catch(Exception e){message.setText("후면 카메라를 열지 못했습니다. 카메라 권한을 확인하고 다른 카메라 앱을 닫은 뒤 다시 시도하세요.");}},ContextCompat.getMainExecutor(this));}
    @Override public void onRequestPermissionsResult(int code,String[] p,int[] result){super.onRequestPermissionsResult(code,p,result);if(code==40){if(result.length>0&&result[0]==PackageManager.PERMISSION_GRANTED)bindCamera();else message.setText("카메라 권한이 필요합니다. 설정 → 앱 → 스쿠터 창고 → 권한에서 카메라를 허용한 뒤 다시 실행하세요.");}}
    void take(){if(shooting||capture==null)return;shooting=true;shutter.setEnabled(false);File dir=new File(getCacheDir(),"vin");dir.mkdirs();shot=new File(dir,"rear-shot.jpg");capture.setTargetRotation(getWindowManager().getDefaultDisplay().getRotation());capture.takePicture(new ImageCapture.OutputFileOptions.Builder(shot).build(),ContextCompat.getMainExecutor(this),new ImageCapture.OnImageSavedCallback(){public void onImageSaved(ImageCapture.OutputFileResults r){shooting=false;if(closed)return;try{showCrop();}catch(Exception e){releaseBitmap();cameraScreen();bindCamera();message.setText("촬영 이미지를 읽지 못했습니다. 다시 촬영하세요.");}}public void onError(ImageCaptureException e){shooting=false;if(closed)return;message.setText("촬영 실패. 다시 시도하세요.");shutter.setEnabled(true);}});}
    void showCrop() throws Exception {cropping=true;if(provider!=null)provider.unbindAll();BitmapFactory.Options opts=new BitmapFactory.Options();opts.inJustDecodeBounds=true;BitmapFactory.decodeFile(shot.getPath(),opts);int sample=1;while(Math.max(opts.outWidth,opts.outHeight)/sample>4096)sample*=2;opts.inJustDecodeBounds=false;opts.inSampleSize=sample;Bitmap decoded=BitmapFactory.decodeFile(shot.getPath(),opts);if(decoded==null)throw new IOException();ExifInterface exif=new ExifInterface(shot.getPath());Matrix m=new Matrix();if(exif.isFlipped())m.postScale(-1,1);m.postRotate(exif.getRotationDegrees());bitmap=Bitmap.createBitmap(decoded,0,0,decoded.getWidth(),decoded.getHeight(),m,true);if(bitmap!=decoded)decoded.recycle();LinearLayout l=root();text(l,"VIN 줄만 선택하세요.\n사진 위를 드래그해 17자리 전체를 감싸세요. NO·배기량·날짜 등은 가능한 한 제외하세요.");crop=new CropView();l.addView(crop,new LinearLayout.LayoutParams(-1,0,1));LinearLayout row=new LinearLayout(this);l.addView(row);button(row,"재촬영",()->{if(shooting)return;releaseBitmap();cameraScreen();bindCamera();});button(row,"취소",this::onBackPressed);button(row,"선택영역 인식",this::finishCrop);}
    void finishCrop(){if(shooting||bitmap==null)return;Rect r=crop.pixels();if(r.width()<170||r.height()<20){Toast.makeText(this,"선택 영역이 너무 작습니다. VIN 전체를 크게 촬영하세요.",Toast.LENGTH_LONG).show();return;}shooting=true;crop.setEnabled(false);final Bitmap selected=Bitmap.createBitmap(bitmap,r.left,r.top,r.width(),r.height());io.execute(()->{File result=new File(getCacheDir(),"vin/capture.jpg");boolean ok=false;try(FileOutputStream out=new FileOutputStream(result)){ok=selected.compress(Bitmap.CompressFormat.JPEG,98,out);}catch(Exception ignored){}if(selected!=bitmap)selected.recycle();final boolean done=ok;runOnUiThread(()->{if(closed)return;if(done){shooting=false;releaseBitmap();setResult(RESULT_OK,new Intent().putExtra("photo",result.getAbsolutePath()));finish();}else{shooting=false;crop.setEnabled(true);Toast.makeText(this,"사진 저장 실패. 다시 시도하세요.",Toast.LENGTH_LONG).show();}});});}
    class CropView extends View {
        final Paint paint=new Paint(3);final RectF display=new RectF(),selection=new RectF(.04f,.38f,.96f,.62f);float sx,sy;
        CropView(){super(VinCameraActivity.this);setContentDescription("VIN 인식 영역 선택. 드래그로 사각형을 지정합니다.");}
        protected void onDraw(Canvas c){super.onDraw(c);if(bitmap==null)return;float scale=Math.min((float)getWidth()/bitmap.getWidth(),(float)getHeight()/bitmap.getHeight());float w=bitmap.getWidth()*scale,h=bitmap.getHeight()*scale;display.set((getWidth()-w)/2,(getHeight()-h)/2,(getWidth()+w)/2,(getHeight()+h)/2);c.drawColor(Color.BLACK);paint.setStyle(Paint.Style.FILL);c.drawBitmap(bitmap,null,display,paint);RectF box=new RectF(display.left+selection.left*w,display.top+selection.top*h,display.left+selection.right*w,display.top+selection.bottom*h);paint.setColor(0x88000000);c.drawRect(display.left,display.top,display.right,box.top,paint);c.drawRect(display.left,box.bottom,display.right,display.bottom,paint);c.drawRect(display.left,box.top,box.left,box.bottom,paint);c.drawRect(box.right,box.top,display.right,box.bottom,paint);paint.setColor(0xff00dfad);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(4);c.drawRect(box,paint);paint.setStyle(Paint.Style.FILL);}
        public boolean onTouchEvent(MotionEvent e){if(!isEnabled()||display.width()<=0)return false;float x=Math.max(0,Math.min(1,(e.getX()-display.left)/display.width())),y=Math.max(0,Math.min(1,(e.getY()-display.top)/display.height()));if(e.getAction()==MotionEvent.ACTION_DOWN){sx=x;sy=y;}if(e.getAction()==MotionEvent.ACTION_MOVE||e.getAction()==MotionEvent.ACTION_UP){if(Math.abs(x-sx)>.01&&Math.abs(y-sy)>.005)selection.set(Math.min(x,sx),Math.min(y,sy),Math.max(x,sx),Math.max(y,sy));invalidate();}if(e.getAction()==MotionEvent.ACTION_UP)performClick();return true;}
        @Override public boolean performClick(){super.performClick();return true;}
        Rect pixels(){int left=Math.max(0,Math.min(bitmap.getWidth()-1,Math.round(selection.left*bitmap.getWidth()))),top=Math.max(0,Math.min(bitmap.getHeight()-1,Math.round(selection.top*bitmap.getHeight())));return new Rect(left,top,Math.max(left+1,Math.min(bitmap.getWidth(),Math.round(selection.right*bitmap.getWidth()))),Math.max(top+1,Math.min(bitmap.getHeight(),Math.round(selection.bottom*bitmap.getHeight()))));}
    }
    @Override public void onConfigurationChanged(Configuration c){super.onConfigurationChanged(c);if(capture!=null)capture.setTargetRotation(getWindowManager().getDefaultDisplay().getRotation());if(crop!=null)crop.invalidate();}
    @Override public void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);if(cropping&&shot!=null)out.putString("shot",shot.getPath());}
    void releaseBitmap(){if(bitmap!=null&&!shooting){bitmap.recycle();bitmap=null;}}
    @Override public void onBackPressed(){if(shooting){Toast.makeText(this,"사진 처리 중입니다.",Toast.LENGTH_SHORT).show();return;}setResult(RESULT_CANCELED);super.onBackPressed();}
    @Override public void onDestroy(){closed=true;if(provider!=null)provider.unbindAll();io.shutdown();if(!shooting)releaseBitmap();if(shot!=null)shot.delete();super.onDestroy();}
}
