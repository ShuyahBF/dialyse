import java.time.Instant

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.shuyah.dialyse"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.shuyah.dialyse"
        minSdk = 24                      // Android 7.0
        targetSdk = 35
        // versionCode : entier qui augmente à chaque version ; versionName : numéro affiché (et envoyé à SAWALI dans le signal de présence)
        versionCode = 4
        versionName = "1.3"
        // Adresses du site et de l'API de Dialyse. Surcharge à la compilation : -PsiteUrl=https://… -PapiUrl=https://…/api
        buildConfigField("String", "SITE_URL", "\"${project.findProperty("siteUrl") ?: "https://looisdialyse.cloud/"}\"")
        buildConfigField("String", "API_URL", "\"${project.findProperty("apiUrl") ?: "https://api.looisdialyse.cloud"}\"")
        // Date et heure de compilation (UTC) : « deploye_le » du signal de présence SAWALI
        buildConfigField("String", "DATE_BUILD", "\"${Instant.now()}\"")
    }

    // ------------------------------------------------------------------------------------------
    // Signature de la version de publication. AUCUNE clé ni mot de passe dans le dépôt : les 4 valeurs sont lues dans des
    // variables d'environnement (ou propriétés Gradle -P…), saisies par le propriétaire :
    //   ANDROID_KEYSTORE_FILE     : chemin du magasin de clés (.p12 créé par Dialyse, ou .jks)
    //   ANDROID_KEYSTORE_PASSWORD : mot de passe du magasin
    //   ANDROID_KEY_ALIAS         : nom de la clé (« shuyah » pour une clé créée par Dialyse)
    //   ANDROID_KEY_PASSWORD      : mot de passe de la clé (le même que celui du magasin pour un .p12)
    // Sans elles : -PsignerAvecCleLocale=true signe avec la clé de TEST de l'environnement (livraison à la main, en attendant la clé permanente).
    // ------------------------------------------------------------------------------------------
    fun valeurSignature(nom: String): String? = ((project.findProperty(nom) as String?) ?: System.getenv(nom))?.takeIf { it.isNotBlank() }
    val cheminCle = valeurSignature("ANDROID_KEYSTORE_FILE")
    val motDePasseFichier = valeurSignature("ANDROID_KEYSTORE_PASSWORD")
    val aliasCle = valeurSignature("ANDROID_KEY_ALIAS")
    val motDePasseCle = valeurSignature("ANDROID_KEY_PASSWORD")
    val signatureDisponible = cheminCle != null && file(cheminCle).exists() && motDePasseFichier != null && aliasCle != null && motDePasseCle != null

    signingConfigs {
        if (signatureDisponible) {
            create("release") {
                storeFile = file(cheminCle!!)
                storePassword = motDePasseFichier
                keyAlias = aliasCle
                keyPassword = motDePasseCle
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true        // R8 : réduit le code
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (signatureDisponible) signingConfig = signingConfigs.getByName("release")
            else if ((project.findProperty("signerAvecCleLocale") as String?) == "true") signingConfig = signingConfigs.getByName("debug")
        }
        debug { isMinifyEnabled = false }
    }

    buildFeatures { buildConfig = true }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-ktx:1.9.1")
    // FragmentActivity récente : exigée pour les demandes de résultat (choix d'un fichier) avec la bibliothèque d'empreinte
    implementation("androidx.fragment:fragment-ktx:1.8.2")
    // Réseau : signal de présence à SAWALI (règle 4)
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    // Empreinte digitale (verrou de l'application)
    implementation("androidx.biometric:biometric:1.1.0")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")   // org.json réel pour les tests JVM
}
