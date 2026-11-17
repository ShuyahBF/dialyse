# Le pont entre le site et le téléphone est appelé PAR SON NOM depuis le JavaScript du site : ses fonctions ne doivent être ni renommées ni supprimées.
-keepclassmembers class com.shuyah.dialyse.Pont { @android.webkit.JavascriptInterface <methods>; }
-keepattributes JavascriptInterface
-dontwarn okhttp3.**
-dontwarn okio.**
