import './signInPage.css';
import { SignIn } from '@clerk/clerk-react';

const SignInPage = () => {
    return (
        <div className='signInPage'>
            <SignIn 
                path="/sign-in" 
                routing="path" 
                signUpUrl="/sign-up" 
                afterSignInUrl="/dashboard"   // توجيه إلى dashboard بعد تسجيل الدخول
            />
        </div>
    );
};
export default SignInPage;