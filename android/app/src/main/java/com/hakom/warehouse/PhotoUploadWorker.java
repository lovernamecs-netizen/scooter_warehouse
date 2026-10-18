package com.hakom.warehouse;
import android.content.Context;
import androidx.work.*;
import org.json.*;
import java.io.*;
import java.net.*;

public class PhotoUploadWorker extends Worker {
 public PhotoUploadWorker(Context c,WorkerParameters p){super(c,p);}
 public Result doWork(){Context c=getApplicationContext();String id=getInputData().getString("id");HttpURLConnection conn=null;
 try{
  if(!PhotoQueue.file(c,id,".json").exists())return Result.success();JSONObject j=PhotoQueue.read(c,id);if("saved".equals(j.optString("status")))return Result.success();
  JSONObject auth=PhotoQueue.session(c);
  if(!auth.optString("origin").equals(j.getString("origin"))||!auth.optString("owner").equals(j.getString("owner"))){PhotoQueue.state(c,id,"login_required","촬영한 계정으로 다시 로그인하세요.");return Result.success();}
  File original=PhotoQueue.file(c,id,".original");if(!original.isFile())throw new IOException("휴대폰 원본 파일이 없습니다.");
  String sha=PhotoQueue.sha(original),boundary="SW"+id;URL url=new URL(j.getString("origin")+"/api/used/"+j.getString("vehicle_id")+"/upload");if(!"https".equals(url.getProtocol()))throw new IOException("HTTPS 서버가 필요합니다.");
  conn=(HttpURLConnection)url.openConnection();conn.setConnectTimeout(20000);conn.setReadTimeout(120000);conn.setInstanceFollowRedirects(false);conn.setRequestMethod("POST");conn.setDoOutput(true);conn.setChunkedStreamingMode(65536);conn.setRequestProperty("Authorization","Bearer "+auth.getString("token"));conn.setRequestProperty("Content-Type","multipart/form-data; boundary="+boundary);
  PhotoQueue.state(c,id,"uploading","");
  try(OutputStream out=conn.getOutputStream()){
   String[] keys={"stay_id","category","key","captured_at","damage_note","damage_status","base_damage"};for(String k:keys)field(out,boundary,k,j.optString(k));field(out,boundary,"upload_id",id);field(out,boundary,"sha256",sha);
   out.write(("--"+boundary+"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"capture.original\"\r\nContent-Type: application/octet-stream\r\n\r\n").getBytes("UTF-8"));try(InputStream in=new FileInputStream(original)){byte[] b=new byte[65536];int n;while((n=in.read(b))>0)out.write(b,0,n);}out.write(("\r\n--"+boundary+"--\r\n").getBytes("UTF-8"));
  }
  int status=conn.getResponseCode();String response="";InputStream stream=status<400?conn.getInputStream():conn.getErrorStream();if(stream!=null)try(InputStream in=stream){response=new String(PhotoQueue.bytes(in,65536),"UTF-8");}
  if(status==200){JSONObject saved=new JSONObject(response);if(!id.equals(saved.optString("id"))||!sha.equals(saved.optString("sha256")))throw new IOException("PC 저장 확인 응답 불일치");PhotoQueue.state(c,id,"saved","");original.delete();return Result.success();}
  if(status==401){PhotoQueue.state(c,id,"login_required","로그인이 만료되었습니다. 다시 로그인하면 재전송합니다.");return Result.success();}
  if(status>=500||status==408||status==429){PhotoQueue.state(c,id,"pending","PC 연결 대기 · "+status);return Result.retry();}
  PhotoQueue.state(c,id,"failed",response);return Result.failure();
 }catch(Exception e){try{PhotoQueue.state(c,id,"pending",e.getMessage()==null?"전송 대기":e.getMessage());}catch(Exception ignored){}return Result.retry();}
 finally{if(conn!=null)conn.disconnect();}
 }
 static void field(OutputStream out,String boundary,String key,String value)throws Exception{out.write(("--"+boundary+"\r\nContent-Disposition: form-data; name=\""+key+"\"\r\n\r\n"+value+"\r\n").getBytes("UTF-8"));}
}
