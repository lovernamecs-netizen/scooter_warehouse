package com.hakom.warehouse;

import android.hardware.biometrics.BiometricManager;
import android.hardware.biometrics.BiometricPrompt;
import android.os.Build;
import android.os.CancellationSignal;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.UUID;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.net.ssl.HttpsURLConnection;
import java.net.URL;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;

/** No reusable plaintext credentials on disk. Every decrypt requires Class 3 biometrics. */
final class BiometricLogin {
 private final MainActivity activity;
 private final SharedPreferences prefs;
 private CancellationSignal cancellation;
 private String pendingAlias;
 private boolean busy;
 private int generation;
 BiometricLogin(MainActivity a){activity=a;prefs=a.getSharedPreferences("biometric_login",0);}
 boolean available(){return Build.VERSION.SDK_INT>=30 && activity.getSystemService(BiometricManager.class).canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG)==BiometricManager.BIOMETRIC_SUCCESS;}
 boolean ready(){return prefs.contains("data")&&activity.origin.equals(prefs.getString("origin",""));}
 private KeyStore store() throws Exception {KeyStore s=KeyStore.getInstance("AndroidKeyStore");s.load(null);return s;}
 private void delete(String alias){if(alias!=null&&!alias.isEmpty())try{store().deleteEntry(alias);}catch(Exception ignored){}}
 void cancel(){generation++;busy=false;if(cancellation!=null)cancellation.cancel();cancellation=null;delete(pendingAlias);pendingAlias=null;}
 void clear(){cancel();delete(prefs.getString("alias",""));prefs.edit().clear().commit();}
 private void reply(String id,String origin,JSONObject result){
  if(activity.web==null||!origin.equals(activity.origin)||!activity.trusted(activity.web.getUrl()))return;
  activity.web.evaluateJavascript("window.onWarehouseBiometric && window.onWarehouseBiometric("+JSONObject.quote(id)+","+result.toString()+")",null);
 }
 private JSONObject result(String field,Object value){JSONObject r=new JSONObject();try{r.put(field,value);}catch(Exception ignored){}return r;}
 void run(String id,String username,String password,boolean enroll){
  final String origin=activity.origin;
  if(busy){reply(id,origin,result("error","생체인증이 진행 중입니다."));return;}
  if(!available()){reply(id,origin,result("error","휴대폰 설정에서 지문을 등록한 뒤 다시 시도하세요."));return;}
  if(!enroll&&!ready()){reply(id,origin,result("error","비밀번호로 로그인하고 생체 로그인을 등록하세요."));return;}
  if(enroll&&(username.isEmpty()||username.length()>200||password.isEmpty()||password.length()>4096)){reply(id,origin,result("error","로그인 정보를 확인하세요."));return;}
  busy=true;final int ticket=++generation;
  try{
   final String alias=enroll?"warehouse-biometric-"+UUID.randomUUID():prefs.getString("alias","");
   if(enroll){
    pendingAlias=alias;
    KeyGenerator generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
    generator.init(new KeyGenParameterSpec.Builder(alias,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
      .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
      .setUserAuthenticationRequired(true).setUserAuthenticationParameters(0,KeyProperties.AUTH_BIOMETRIC_STRONG)
      .setInvalidatedByBiometricEnrollment(true).build());generator.generateKey();
   }
   Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");SecretKey key=(SecretKey)store().getKey(alias,null);
   if(enroll)cipher.init(Cipher.ENCRYPT_MODE,key);
   else cipher.init(Cipher.DECRYPT_MODE,key,new GCMParameterSpec(128,Base64.decode(prefs.getString("iv",""),Base64.NO_WRAP)));
   cancellation=new CancellationSignal();
   new BiometricPrompt.Builder(activity).setTitle(enroll?"생체 로그인 등록":"스쿠터 창고 로그인")
    .setSubtitle("등록된 지문으로 인증하세요")
    .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
    .setNegativeButton("취소",activity.getMainExecutor(),(dialog,which)->{if(ticket!=generation)return;cancel();reply(id,origin,result("error","생체인증을 취소했습니다."));})
    .build().authenticate(new BiometricPrompt.CryptoObject(cipher),cancellation,activity.getMainExecutor(),new BiometricPrompt.AuthenticationCallback(){
     @Override public void onAuthenticationError(int code,CharSequence message){
      if(ticket!=generation)return;busy=false;delete(pendingAlias);pendingAlias=null;
      reply(id,origin,result("error",code==BiometricPrompt.BIOMETRIC_ERROR_USER_CANCELED||code==BiometricPrompt.BIOMETRIC_ERROR_CANCELED?"생체인증을 취소했습니다.":"생체인증을 사용할 수 없습니다. 비밀번호로 로그인하세요."));
     }
     @Override public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult auth){
      if(ticket!=generation)return;
      try{
       Cipher unlocked=auth.getCryptoObject().getCipher();unlocked.updateAAD(origin.getBytes(StandardCharsets.UTF_8));
       if(enroll){
        JSONObject credentials=new JSONObject();credentials.put("username",username);credentials.put("password",password);
        String encrypted=Base64.encodeToString(unlocked.doFinal(credentials.toString().getBytes(StandardCharsets.UTF_8)),Base64.NO_WRAP);
        String old=prefs.getString("alias","");
        if(!prefs.edit().putString("origin",origin).putString("alias",alias).putString("iv",Base64.encodeToString(unlocked.getIV(),Base64.NO_WRAP)).putString("data",encrypted).commit())throw new Exception();
        pendingAlias=null;delete(old);busy=false;reply(id,origin,result("enrolled",true));
       }else{
        byte[] credentials=unlocked.doFinal(Base64.decode(prefs.getString("data",""),Base64.NO_WRAP));
        new Thread(()->login(id,origin,ticket,credentials),"biometric-login").start();
       }
      }catch(Exception e){busy=false;delete(pendingAlias);pendingAlias=null;reply(id,origin,result("error","생체 로그인 정보를 다시 등록하세요."));}
     }
    });
  }catch(Exception e){busy=false;delete(pendingAlias);pendingAlias=null;if(!enroll)clear();reply(id,origin,result("error","지문 또는 보안 설정이 변경되었습니다. 비밀번호로 로그인해 다시 등록하세요."));}
 }
 private void login(String id,String origin,int ticket,byte[] credentials){
  JSONObject response;HttpsURLConnection connection=null;boolean revoked=false;
  try{
   connection=(HttpsURLConnection)new URL(origin+"/api/login").openConnection();
   connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(15000);connection.setReadTimeout(20000);
   connection.setRequestMethod("POST");connection.setDoOutput(true);connection.setRequestProperty("Content-Type","application/json");
   try(java.io.OutputStream out=connection.getOutputStream()){out.write(credentials);}
   int status=connection.getResponseCode();
   if(status==200){
    try(InputStream in=connection.getInputStream();ByteArrayOutputStream out=new ByteArrayOutputStream()){
     byte[] buffer=new byte[2048];int n;while((n=in.read(buffer))!=-1){if(out.size()+n>65536)throw new Exception();out.write(buffer,0,n);}
     JSONObject body=new JSONObject(out.toString("UTF-8"));String token=body.getString("token");if(token.isEmpty()||token.length()>4096)throw new Exception();response=result("token",token);
    }
   }else{revoked=status==401||status==403;response=result("error",revoked?"계정 또는 비밀번호가 변경되었습니다. 비밀번호로 다시 로그인하세요.":"서버 로그인을 완료하지 못했습니다. 잠시 후 다시 시도하세요.");}
  }catch(Exception e){response=result("error","서버에 연결할 수 없습니다. 네트워크 연결을 확인하세요.");}
  finally{java.util.Arrays.fill(credentials,(byte)0);if(connection!=null)connection.disconnect();}
  final JSONObject answer=response;final boolean remove=revoked;
  activity.runOnUiThread(()->{if(ticket!=generation)return;busy=false;if(remove)clear();reply(id,origin,answer);});
 }
}
