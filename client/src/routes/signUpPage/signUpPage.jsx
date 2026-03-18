import './signUpPage.css';
import { SignUp } from '@clerk/clerk-react';

const SignUpPage = () => {
    return (
        <div className='signUpPage'>
            <SignUp 
                path="/sign-up" 
                routing="path" 
                signInUrl="/sign-in" 
                afterSignUpUrl="/dashboard"   // توجيه إلى dashboard بعد إنشاء الحساب
            />
        </div>
    );
};
export default SignUpPage;