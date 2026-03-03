/**
 * Icons — React Icons + Custom Spiritual SVGs
 */

import {
    FiUpload, FiSun, FiMoon, FiTrash2, FiRefreshCw, FiPlay, FiPause, FiSquare,
    FiVolume2, FiVolumeX, FiLoader, FiAlertCircle, FiCheckCircle, FiClock,
    FiChevronDown, FiChevronUp, FiChevronLeft, FiSend, FiX, FiSettings, FiInfo,
    FiSearch, FiArrowLeft, FiFileText, FiMessageCircle, FiBook, FiBookOpen,
    FiList, FiMic, FiVideo, FiMusic, FiGlobe,
    FiMoreVertical, FiHelpCircle, FiUser, FiLogIn, FiLogOut, FiHeart, FiUserPlus,
    FiCopy, FiCheck, FiRotateCcw
} from 'react-icons/fi';

import {
    HiOutlineSparkles, HiOutlineLightBulb, HiOutlineTranslate,
    HiOutlineDocumentText
} from 'react-icons/hi';

/* Custom OM (ॐ) symbol — a proper spiritual identity */
const OmIcon = ({ size = 24, ...props }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
        <text x="50%" y="54%" dominantBaseline="middle" textAnchor="middle"
              fontSize="18" fontWeight="700" fill="currentColor"
              fontFamily="'Noto Sans Devanagari', serif">ॐ</text>
    </svg>
);

export const Icons = {
    // Brand
    Logo: OmIcon,
    Spiritual: OmIcon,

    // Theme
    Sun: FiSun,
    Moon: FiMoon,

    // Actions
    Upload: FiUpload,
    Send: FiSend,
    Delete: FiTrash2,
    Refresh: FiRefreshCw,
    Close: FiX,
    Settings: FiSettings,
    Info: FiInfo,
    MoreVertical: FiMoreVertical,
    Search: FiSearch,
    Back: FiArrowLeft,

    // Media
    Play: FiPlay,
    Pause: FiPause,
    Stop: FiSquare,
    VolumeOn: FiVolume2,
    VolumeOff: FiVolumeX,
    Mic: FiMic,
    Video: FiVideo,
    Music: FiMusic,

    // Status
    Loading: FiLoader,
    Error: FiAlertCircle,
    Success: FiCheckCircle,
    Clock: FiClock,

    // Content
    Transcript: FiFileText,
    Summary: HiOutlineDocumentText,
    Explanation: HiOutlineLightBulb,
    Chat: FiMessageCircle,
    Question: FiHelpCircle,
    Book: FiBook,
    BookOpen: FiBookOpen,
    List: FiList,
    Sessions: FiBook,

    // Features
    Sparkles: HiOutlineSparkles,
    Translate: HiOutlineTranslate,
    Speak: FiVolume2,
    AI: HiOutlineSparkles,
    Globe: FiGlobe,

    // Chevrons
    ChevronDown: FiChevronDown,
    ChevronUp: FiChevronUp,
    ChevronLeft: FiChevronLeft,

    // Processing
    Processing: FiLoader,
    Done: FiCheckCircle,
    Pending: FiClock,

    // Auth & User
    User: FiUser,
    Login: FiLogIn,
    Logout: FiLogOut,
    Heart: FiHeart,
    UserPlus: FiUserPlus,

    // Chat Actions
    Copy: FiCopy,
    Check: FiCheck,
    Retry: FiRotateCcw,
};

export default Icons;
