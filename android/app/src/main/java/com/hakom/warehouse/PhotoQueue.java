package com.hakom.warehouse;
import android.content.*;
import android.util.*;
import android.security.keystore.*;
import androidx.work.*;
import org.json.*;
import java.io.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;

/** Private persistent originals and atomic job manifests. Never stored in cacheDir. */
public final class PhotoQueue {
 static byte[] bytes(InputStream in,int limit)throws IOException{ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[8192];int n;while((n=in.read(b,0,Math.min(b.length,limit-out.size())))>0)out.write(b,0,n);return out.toByteArray();}
 static File dir(Context c){File f=new File(c.getFilesDir(),"photo_queue");f.mkdirs();return f;}
 static File file(Context c,String id,String suffix){return new File(dir(c),UUID.fromString(id).toString()+suffix);}
 static synchronized void write(Context c,JSONObject j)throws Exception{AtomicFile a=new AtomicFile(file(c,j.getString("id"),".json"));FileOutputStream o=a.startWrite();try{o.write(j.toString().getBytes("UTF-8"));a.finishWrite(o);}catch(Exception e){a.failWrite(o);throw e;}}
 static synchronized JSONObject read(Context c,String id)throws Exception{try(InputStream in=new AtomicFile(file(c,id,".json")).openRead()){return new JSONObject(new String(PhotoQueue.bytes(in,1000000),"UTF-8"));}}
 static synchronized JSONArray list(Context c,String origin,String owner){JSONArray out=new JSONArray();File[] fs=dir(c).listFiles((d,n)->n.endsWith(".json"));if(fs!=null)for(File f:fs)try{JSONObject j=read(c,f.getName().replace(".json",""));if(j.optString("origin").equals(origin)&&j.optString("owner").equals(owner))out.put(j);}catch(Exception ignored){}return out;}
 static javax.crypto.SecretKey key()throws Exception{KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);if(!ks.containsAlias("warehouse-photo-session")){KeyGenerator g=KeyGenerator.getInstance("AES","AndroidKeyStore");g.init(new KeyGenParameterSpec.Builder("warehouse-photo-session",KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());g.generateKey();}return (javax.crypto.SecretKey)ks.getKey("warehouse-photo-session",null);}
 static synchronized void session(Context c,String origin,String owner,String token)throws Exception{SharedPreferences p=c.getSharedPreferences("photo_auth",0);if(token.isEmpty()){p.edit().clear().commit();return;}JSONObject j=new JSONObject();j.put("origin",origin);j.put("owner",owner);j.put("token",token);Cipher x=Cipher.getInstance("AES/GCM/NoPadding");x.init(Cipher.ENCRYPT_MODE,key());p.edit().putString("iv",android.util.Base64.encodeToString(x.getIV(),android.util.Base64.NO_WRAP)).putString("data",android.util.Base64.encodeToString(x.doFinal(j.toString().getBytes("UTF-8")),android.util.Base64.NO_WRAP)).commit();resume(c,origin,owner);}
 static synchronized JSONObject session(Context c)throws Exception{SharedPreferences p=c.getSharedPreferences("photo_auth",0);if(!p.contains("data"))return new JSONObject();Cipher x=Cipher.getInstance("AES/GCM/NoPadding");x.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,android.util.Base64.decode(p.getString("iv",""),0)));return new JSONObject(new String(x.doFinal(android.util.Base64.decode(p.getString("data",""),0)),"UTF-8"));}
 static void enqueue(Context c,String id){OneTimeWorkRequest work=new OneTimeWorkRequest.Builder(PhotoUploadWorker.class).setInputData(new Data.Builder().putString("id",id).build()).setConstraints(new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).setBackoffCriteria(BackoffPolicy.EXPONENTIAL,30,TimeUnit.SECONDS).build();WorkManager.getInstance(c).enqueueUniqueWork("photo-"+id,ExistingWorkPolicy.KEEP,work);}
 static void resume(Context c,String origin,String owner){JSONArray jobs=list(c,origin,owner);for(int i=0;i<jobs.length();i++){JSONObject j=jobs.optJSONObject(i);if(Arrays.asList("pending","uploading","login_required").contains(j.optString("status")))enqueue(c,j.optString("id"));}}
 static String sha(File f)throws Exception{MessageDigest h=MessageDigest.getInstance("SHA-256");try(InputStream in=new FileInputStream(f)){byte[] b=new byte[65536];int n;while((n=in.read(b))>0)h.update(b,0,n);}StringBuilder s=new StringBuilder();for(byte b:h.digest())s.append(String.format(Locale.ROOT,"%02x",b));return s.toString();}
 static synchronized void state(Context c,String id,String state,String message)throws Exception{JSONObject j=read(c,id);j.put("status",state);j.put("message",message);write(c,j);}
}
